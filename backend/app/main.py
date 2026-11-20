
import logging
import re
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
import time
from dotenv import load_dotenv
from app.api.auth import router as auth_router
from app.api.conversations import router as conversations_router


# =====================================================
# CONFIGURATION
# =====================================================

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("emsi-chatbot")

app = FastAPI(
    title="EMSI-ChatBot API",
    version="1.1.0"
)
app.include_router(auth_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")

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
IMAGE_DIR = PROCESSED_DIR / "Brochure-EMSI" / "images"

PROCESSED_DIR.mkdir(
    parents=True,
    exist_ok=True
)

@app.get("/images/{image_path:path}", include_in_schema=False)
def serve_brochure_image(image_path: str):
    """Serve only indexed brochure image files, never arbitrary processed data."""
    root = IMAGE_DIR.resolve()
    candidate = (PROCESSED_DIR / image_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Image not found.")
    if candidate.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=404, detail="Image not found.")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    return FileResponse(candidate)


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


@app.middleware("http")
async def limit_vision_upload_body(request, call_next):
    """Reject oversized declared multipart bodies before parsing/spooling them."""
    if request.method == "POST" and request.url.path.endswith("/vision"):
        from app.services.vision_service import max_upload_bytes

        raw_length = request.headers.get("content-length")
        if raw_length and raw_length.isdigit():
            # Allow bounded multipart headers around the configured file limit.
            if int(raw_length) > max_upload_bytes() + 64 * 1024:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "L'image dépasse la taille maximale autorisée."},
                )
    return await call_next(request)


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
    *,
    return_evidence: bool = False,
):
    from app.services.unavailable_answer import (
        has_explicit_admission_criteria,
        is_admission_question,
        unavailable_answer,
    )

    from app.rag.isolated_retriever import (
        search_documents_isolated
    )

    start_total = time.perf_counter()

    logger.info("Recherche textuelle demandée (question_chars=%d)", len(question))

    from app.rag.ranking_policy import (
        is_exhaustive_program_question,
        is_program_duration_question,
    )
    from app.rag.conversation import requested_campus_offerings
    campus_offering_target = requested_campus_offerings(question, history)
    exhaustive_program_list = (
        is_exhaustive_program_question(question)
        and not campus_offering_target
    )
    program_duration_query = (
        is_program_duration_question(question)
        and not campus_offering_target
    )
    preserve_program_catalog = exhaustive_program_list or program_duration_query
    retrieval_limit = 10 if exhaustive_program_list else 8
    selected_limit = 8 if preserve_program_catalog else 4

    # Récupération de davantage de candidats.
    start_search = time.perf_counter()

    documents = search_documents_isolated(
        retrieval_query,
        limit=retrieval_limit
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
    selected_documents = select_relevant_documents(
        documents,
        limit=selected_limit,
        preserve_catalog_evidence=preserve_program_catalog,
    )
    if exhaustive_program_list:
        selected_documents.sort(
            key=lambda document: not document.get("catalog_evidence", False)
        )
        logger.info(
            "[RAG_EXHAUSTIVE] groq_context_candidates=%s",
            [
                {"id": document.get("id"), "page": document.get("page"),
                 "chunk_index": document.get("chunk_index"),
                 "score": document.get("score"),
                 "excerpt": str(document.get("content", ""))[:240]}
                for document in selected_documents
            ],
        )
    if (
        is_admission_question(question)
        and not has_explicit_admission_criteria(selected_documents)
    ):
        # Keep autobiographical mentions such as "admission directe" and
        # generic apply calls from being treated as admissions requirements.
        answer = unavailable_answer(question)
        source_documents = []
    elif campus_offering_target:
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
                answer = unavailable_answer(question)
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
                answer = unavailable_answer(question)
        else:
            answer = unavailable_answer(question)
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
            answer = unavailable_answer(question)

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

    if return_evidence:
        return answer, sources, selected_documents
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

@lru_cache(maxsize=40)
def get_cached_images(question: str, mode: str = "generic"):
    from app.rag.isolated_clip import (
        search_images_isolated
    )

    logger.info("Recherche d'images CLIP demandée")

    return search_images_isolated(
        question,
        limit=10,
        mode=mode,
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
    from app.rag.image_intent import (
        image_matches_person_evidence,
        resolve_image_intent,
    )
    image_intent = resolve_image_intent(question, history)
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
        selected_documents = []
        image_search_requested = request.include_images and image_intent.requested
        person_evidence_required = image_search_requested and bool(image_intent.person_target)

        # For non-person image requests, the final response is based on CLIP
        # candidates plus same-page brochure evidence. The text answer was
        # discarded unconditionally after image selection, so avoid loading
        # BGE/Groq on this path. Person identification still requires its
        # separate, strict text-and-caption evidence check.
        if person_evidence_required:
            # Person-image matching requires explicit same-page document evidence.
            answer, sources, selected_documents = _compute_rag_answer(
                question, request.use_llm, retrieval_query, history,
                return_evidence=True,
            )
        elif image_search_requested:
            answer, sources = "", []
        elif history:
            # Stateful requests bypass the process-wide answer cache.
            answer, sources = _compute_rag_answer(
                question, request.use_llm, retrieval_query, history
            )
        else:
            answer, sources = get_cached_rag_answer(question, request.use_llm)

        # 2. Recherche visuelle CLIP.
        images = []

        if request.include_images and image_intent.requested:
            candidates = []
            image_search_failed = False
            try:
                # The CLIP launcher confirms BGE-M3 release and safe RAM first.
                candidates = (
                    []
                    if image_intent.person_target and not selected_documents
                    else get_cached_images(image_intent.query, image_intent.mode)
                )
                if image_intent.person_target:
                    images = [
                        image for image in candidates
                        if image_matches_person_evidence(
                            image, selected_documents, image_intent.person_target
                        )
                    ][:3]
                    if not images:
                        answer = _person_photo_not_verified()
                        sources = []
                else:
                    from app.rag.image_evidence import image_candidate_decision, select_diverse_images
                    relevant_images = []
                    candidate_diagnostics = []
                    for candidate in candidates:
                        relevant, _page_excerpt, reason = image_candidate_decision(
                            candidate, image_intent, selected_documents
                        )
                        candidate_diagnostics.append({
                            "id": candidate.get("id"),
                            "source": candidate.get("source"),
                            "page": candidate.get("page"),
                            "score": round(float(candidate.get("score", 0.0)), 4),
                            "visual_margin": candidate.get("visual_margin"),
                            "width": candidate.get("width"),
                            "height": candidate.get("height"),
                            "reason": reason,
                        })
                        if not relevant:
                            continue
                        image = dict(candidate)
                        relevant_images.append(image)
                    # The CLIP worker sorts by score and keeps one candidate
                    # per page; retain that order and cap the UI gallery.
                    images = select_diverse_images(relevant_images, limit=3)
                    logger.info("CLIP décisions candidats : mode=%s, décisions=%s",
                                image_intent.mode, candidate_diagnostics)

                logger.info(
                    "CLIP pertinence : mode=%s, candidats=%d, retenus=%d, "
                    "scores=%s, pages=%s",
                    image_intent.mode,
                    len(candidates),
                    len(images),
                    [round(float(item.get("score", 0.0)), 3) for item in candidates[:10]],
                    [item.get("page") for item in candidates[:10]],
                )

            except Exception as exc:
                image_search_failed = True
                # Une erreur CLIP ne doit pas
                # empêcher la réponse textuelle.
                from app.rag.isolated_clip import ClipSearchDeferred
                if isinstance(exc, ClipSearchDeferred):
                    logger.warning("Recherche CLIP différée : %s", exc)
                else:
                    logger.exception("Recherche CLIP indisponible")
                # Preserve the previous text fallback if image search cannot
                # run, while keeping successful image-only requests lean.
                if image_search_requested and not person_evidence_required:
                    answer, sources = _compute_rag_answer(
                        question, request.use_llm, retrieval_query, history
                    )
                answer = _image_search_unavailable(answer)
            if (
                image_intent.person_target
                and not images
                and not image_search_failed
            ):
                answer = _person_photo_not_verified()
                sources = []
            elif not images and not image_search_failed:
                if image_search_requested and not person_evidence_required:
                    # Keep the previous text-source fallback when CLIP ran
                    # successfully but found no image that passed validation.
                    answer, sources = _compute_rag_answer(
                        question, request.use_llm, retrieval_query, history
                    )
                answer = _no_relevant_image_answer(image_intent.mode)
            elif images:
                image_sources = []
                seen = set()
                for image in images:
                    identity = (str(image.get("source", "")).casefold(), str(image.get("page", "")))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    image_sources.append({
                        "source": image.get("source", ""),
                        "page": image.get("page", 0),
                        "score": image.get("score", 0.0),
                    })
                sources = image_sources
                answer = _answer_for_images(image_intent.mode, images)

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


def _person_photo_not_verified() -> str:
    return (
        "Je n’ai pas trouvé dans la brochure de photo explicitement associée "
        "à cette personne."
    )


def _image_search_unavailable(answer: str) -> str:
    notice = "La recherche d’images est temporairement indisponible; la réponse textuelle reste disponible."
    return answer.rstrip() + "\n\n" + notice


def _no_relevant_image_answer(mode: str) -> str:
    if mode == "campus":
        return "Je n’ai pas retrouvé d’image suffisamment pertinente d’un campus EMSI dans les images indexées de la brochure."
    if mode == "laboratory":
        return "Je n’ai pas retrouvé d’image suffisamment pertinente d’un laboratoire EMSI dans les images indexées de la brochure."
    if mode == "event":
        return "Je n’ai pas retrouvé d’image suffisamment pertinente de cet événement dans les images indexées de la brochure."
    return "Je n’ai pas retrouvé d’image suffisamment pertinente dans les images indexées de la brochure EMSI."


def _answer_for_images(mode: str, images: list[dict]) -> str:
    pages = ", ".join(str(image.get("page", "?")) for image in images)
    if mode == "campus":
        captions = [
            str(image.get("caption", ""))
            for image in images
            if image.get("caption_verified") is True
            and re.search(r"\b(campus|site|b[aâ]timent)\b", str(image.get("caption", "")), re.I)
        ]
        if any(re.search(r"\b(photo|photographie)\b", caption, re.I) for caption in captions):
            return f"Voici une photo explicitement légendée comme représentant un campus EMSI (page {pages})."
        if captions:
            return f"La légende identifie ce visuel comme lié à un campus EMSI (page {pages})."
        return f"J’ai trouvé un visuel de la brochure, mais aucune légende ne confirme qu’il représente un campus EMSI (page {pages})."
    if mode == "laboratory":
        verified_laboratory_caption = any(
            image.get("caption_verified") is True
            and re.search(r"\b(laboratoire|labo|travaux pratiques|atelier)\b", str(image.get("caption", "")), re.I)
            for image in images
        )
        if verified_laboratory_caption:
            return f"Voici une image explicitement légendée comme liée à un laboratoire ou à une activité pratique (pages {pages})."
        return f"J’ai trouvé des visuels sur des pages consacrées aux activités techniques ou aux laboratoires; les images ne sont pas légendées individuellement (pages {pages})."
    if mode == "event":
        verified_event_caption = any(
            image.get("caption_verified") is True
            and re.search(r"\b(evenement|événement|conference|conférence|ceremonie|cérémonie|diplome|diplôme|forum)\b", str(image.get("caption", "")), re.I)
            for image in images
        )
        if verified_event_caption:
            return f"Voici une image légendée comme liée à l’événement demandé (pages {pages})."
        return f"J’ai trouvé des visuels sur les pages indiquées, mais aucune légende ne permet d’identifier l’événement (pages {pages})."
    if mode == "person":
        return f"Voici une photo explicitement légendée et associée à la personne dans la brochure (page {pages})."
    if mode == "brochure":
        return f"Voici quelques visuels extraits de la brochure EMSI, avec leurs pages : {pages}."
    return f"Voici quelques visuels pertinents de la brochure EMSI, pages {pages}."


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
        and path.stat().st_size >= 16 * 1024
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
