
import logging
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import time
from dotenv import load_dotenv


# =====================================================
# CONFIGURATION
# =====================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("emsi-chatbot")

app = FastAPI(
    title="EMSI-ChatBot API",
    version="1.1.0"
)

# Un seul traitement lourd à la fois.
rag_lock = Lock()


# =====================================================
# CHEMINS
# =====================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

PROCESSED_DIR = (
    PROJECT_ROOT / "data" / "processed"
)

PROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True
)

app.mount(
    "/images",
    StaticFiles(
        directory=str(PROCESSED_DIR),
        check_dir=True
    ),
    name="images"
)


# =====================================================
# CORS
# =====================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"]
)


# =====================================================
# MODÈLES PYDANTIC
# =====================================================

class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class ChatRequest(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=1000
    )

    use_llm: bool = False

    # Désactiver si aucune image n'est nécessaire.
    include_images: bool = False
    history: list[ConversationTurn] = Field(default_factory=list, max_length=10)


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict]
    images: list[dict]


# =====================================================
# ROUTES DE BASE
# =====================================================

@app.get("/")
def home():
    return {
        "message": "Bienvenue sur EMSI-ChatBot"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


# =====================================================
# RECHERCHE RAG TEXTUELLE
# =====================================================


def _compute_rag_answer(
    question: str,
    use_llm: bool,
    retrieval_query: str,
    history: tuple[dict[str, str], ...] = (),
):
    from app.rag.isolated_retriever import (
        search_documents_isolated
    )

    start_total = time.perf_counter()

    logger.info("Recherche textuelle demandée (question_chars=%d)", len(question))

    # Récupération de davantage de candidats.
    start_search = time.perf_counter()

    documents = search_documents_isolated(
        retrieval_query,
        limit=8
    )

    search_duration = (
        time.perf_counter() - start_search
    )

    logger.info(
        "Recherche BGE-M3 : %.2f secondes",
        search_duration
    )

    # Sélection de passages pour la génération.
    from app.rag.conversation import (
        campus_offering_evidence_documents,
        has_general_offering_information,
        requested_campus_offerings,
        select_relevant_documents,
    )
    selected_documents = select_relevant_documents(documents, limit=4)
    campus_offering_target = requested_campus_offerings(question, history)
    if campus_offering_target:
        # Use only selected passages containing an explicit, same-sentence
        # campus-to-offering relationship. Local offering answers are quoted
        # verbatim so Groq cannot expand a partial local list with general EMSI courses.
        local_offerings = campus_offering_evidence_documents(
            selected_documents, campus_offering_target
        )
        general_offering_count = sum(
            has_general_offering_information([document])
            for document in selected_documents
        )
        logger.info(
            "Offre locale diagnostic : campus=%s, candidats=%d, retenus=%d, "
            "scores_retenus=%s, preuves_locales=%d, passages_generaux=%d, groq_bypassed=true",
            campus_offering_target,
            len(documents),
            len(selected_documents),
            [round(float(document["score"]), 3) for document in selected_documents],
            len(local_offerings),
            general_offering_count,
        )
        if local_offerings:
            cited_offerings = [
                document for document in local_offerings
                if document.get("source") and document.get("page") not in (None, "")
            ]
            if cited_offerings:
                answer = (
                    f"Pour le campus EMSI de {campus_offering_target}, la brochure indique : "
                    + " ".join(
                        f"« {document['content']} » "
                        f"({document['source']}, page {document['page']})."
                        for document in cited_offerings
                    )
                )
                source_documents = cited_offerings
            else:
                answer = "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
                source_documents = []
        elif has_general_offering_information(selected_documents):
            general_sources = [
                document for document in selected_documents
                if has_general_offering_information([document])
                and document.get("source")
                and document.get("page") not in (None, "")
            ]
            source_documents = general_sources[:1]
            if source_documents:
                document = source_documents[0]
                answer = (
                    "Les passages consultés mentionnent des formations EMSI, mais ne permettent pas de confirmer "
                    f"lesquelles sont spécifiquement proposées sur le campus EMSI de {campus_offering_target}. "
                    f"({document['source']}, page {document['page']})."
                )
            else:
                answer = "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
        else:
            answer = "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
            source_documents = []
    elif use_llm:
        from app.services.groq_service import (
            build_context_with_references,
            generate_answer,
            get_cited_documents,
        )

        start_llm = time.perf_counter()

        answer = generate_answer(
            question,
            selected_documents,
            history=history,
        )
        _, references = build_context_with_references(selected_documents)
        source_documents = get_cited_documents(answer, references)

        llm_duration = (
            time.perf_counter() - start_llm
        )

        logger.info(
            "Génération Groq : %.2f secondes",
            llm_duration
        )

    else:
        source_documents = selected_documents
        if selected_documents:
            passages = "\n\n".join(
                f"Page {doc.get('page', 0)} : "
                f"{doc.get('content', '')[:350]}"
                for doc in selected_documents
            )

            answer = (
                "Voici les passages retrouvés "
                "dans la brochure EMSI :\n\n"
                + passages
            )
        else:
            answer = (
                "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
            )

    sources = [
        {
            "source": doc.get("source", ""),
            "page": doc.get("page", 0),
            "score": doc.get("score", 0.0)
        }
        for doc in source_documents
    ]

    total_duration = (
        time.perf_counter() - start_total
    )

    logger.info(
        "RAG total : %.2f secondes",
        total_duration
    )

    return answer, sources


@lru_cache(maxsize=20)
def get_cached_rag_answer(question: str, use_llm: bool):
    """Cache only stateless requests so conversation history is never retained server-side."""
    from app.rag.conversation import build_retrieval_query
    retrieval_query = build_retrieval_query(question, ())
    return _compute_rag_answer(question, use_llm, retrieval_query, ())


# =====================================================
# RECHERCHE D'IMAGES CLIP
# =====================================================

@lru_cache(maxsize=20)
def get_cached_images(question: str):
    from app.rag.isolated_clip import (
        search_images_isolated
    )

    logger.info("Recherche d'images CLIP demandée")

    return search_images_isolated(
        question,
        limit=3
    )


# =====================================================
# ROUTE CHAT MULTIMODALE
# =====================================================

@app.post(
    "/api/chat",
    response_model=ChatResponse
)
def chat(request: ChatRequest):
    question = " ".join(
        request.question.split()
    )
    from app.rag.conversation import (
        build_retrieval_query,
        normalize_history,
        requested_campus_offerings,
    )
    history = tuple(normalize_history(request.history))
    retrieval_query = build_retrieval_query(question, history)
    campus_offering_target = requested_campus_offerings(question, history)
    logger.info(
        "Chat diagnostic : history_messages=%d, cache_policy=%s, campus_offering_target=%s",
        len(history),
        "bypass-history" if history else "stateless-cache",
        campus_offering_target or "none",
    )

    if not question:
        raise HTTPException(
            status_code=422,
            detail="La question ne peut pas être vide."
        )

    if not rag_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail=(
                "Le chatbot traite déjà une question. "
                "Veuillez réessayer dans quelques instants."
            )
        )

    try:
        # 1. Recherche textuelle + génération optionnelle Groq.
        if history:
            # Stateful requests bypass the process-wide answer cache.
            answer, sources = _compute_rag_answer(
                question, request.use_llm, retrieval_query, history
            )
        else:
            answer, sources = get_cached_rag_answer(question, request.use_llm)

        # 2. Recherche visuelle CLIP.
        images = []

        if request.include_images:
            try:
                # The CLIP launcher confirms BGE-M3 release and safe RAM first.
                images = get_cached_images(
                    question
                )

            except Exception as exc:
                # Une erreur CLIP ne doit pas
                # empêcher la réponse textuelle.
                from app.rag.isolated_clip import ClipSearchDeferred
                if isinstance(exc, ClipSearchDeferred):
                    logger.warning("Recherche CLIP différée : %s", exc)
                else:
                    logger.exception("Recherche CLIP indisponible")

        # 3. Réponse multimodale.
        return ChatResponse(
            answer=answer,
            sources=sources,
            images=images
        )

    except Exception as exc:
        from app.services.groq_service import GroqAPIError
        if isinstance(exc, GroqAPIError):
            logger.warning("Échec du fournisseur Groq : %s", exc)
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        logger.exception(
            "Erreur pendant le traitement RAG"
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Erreur interne pendant "
                "le traitement RAG."
            )
        )

    finally:
        rag_lock.release()


# =====================================================
# STATISTIQUES DU CACHE
# =====================================================

@app.get("/api/cache/stats")
def cache_stats():
    text_info = (
        get_cached_rag_answer.cache_info()
    )

    image_info = (
        get_cached_images.cache_info()
    )

    return {
        "text": {
            "hits": text_info.hits,
            "misses": text_info.misses,
            "maxsize": text_info.maxsize,
            "currsize": text_info.currsize
        },
        "images": {
            "hits": image_info.hits,
            "misses": image_info.misses,
            "maxsize": image_info.maxsize,
            "currsize": image_info.currsize
        }
    }


# =====================================================
# GALERIE D'IMAGES
# =====================================================

@app.get("/api/images")
def get_images(limit: int = 10):
    image_dir = (
        PROCESSED_DIR
        / "Brochure-EMSI"
        / "images"
    )

    if not image_dir.exists():
        return {
            "images": []
        }

    image_files = sorted(
        path
        for path in image_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        }
    )

    safe_limit = max(
        0,
        min(limit, 50)
    )

    images = [
        {
            "filename": path.name,
            "url": (
                "/images/Brochure-EMSI/images/"
                + path.name
            )
        }
        for path in image_files[:safe_limit]
    ]

    return {
        "images": images
    }


# =====================================================
# ROUTE TEST FLUTTER
# =====================================================

@app.post("/api/chat/test")
def chat_test(request: ChatRequest):
    return {
        "answer": (
            "Connexion Flutter-FastAPI réussie ! "
            f"Question reçue : {request.question}"
        ),
        "sources": [],
        "images": []
    }
