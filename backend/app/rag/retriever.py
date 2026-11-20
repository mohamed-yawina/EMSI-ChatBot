
import os
import re
import logging
import unicodedata
from functools import lru_cache

import torch
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
import time

from app.rag.ranking_policy import (
    campus_list_bonus,
    is_exhaustive_program_question,
    is_program_duration_question,
    program_catalog_bonus,
    program_duration_catalog_bonus,
    repair_common_mojibake,
    should_apply_program_topic_bonus,
)


# =====================================================
# CONFIGURATION
# =====================================================

logger = logging.getLogger(__name__)

QDRANT_URL = os.getenv(
    "EMSI_QDRANT_URL",
    "http://127.0.0.1:6333"
)

TEXT_COLLECTION = "emsi_text"
BGE_MODEL = "BAAI/bge-m3"

MAX_CPU_THREADS = 2
MAX_CANDIDATES = 60

SEMANTIC_WEIGHT = 0.65
LEXICAL_WEIGHT = 0.35

MAX_PASSAGES_PER_PAGE = 2


# =====================================================
# STOPWORDS
# =====================================================

STOPWORDS = {
    "les", "des", "une", "dans", "pour",
    "avec", "sont", "quelles", "quels",
    "quelle", "quel", "vous", "nous",
    "comment", "est", "par", "sur",
    "emsi", "ecole", "proposees",
    "proposes", "aux", "ces", "ses",
    "qui", "que", "quoi", "leur",
    "leurs", "plus", "cette", "cet",
    "parmi", "tous", "toutes", "disponibles",
    "disponible", "avoir", "etre", "fait",
    "elle", "ils", "elles", "dont"
}


# =====================================================
# SYNONYMES
# =====================================================

SYNONYMS = {
    "formations": {
        "formation", "formations",
        "filiere", "filieres",
        "specialite", "specialites",
        "cursus"
    },

    "campus": {
        "campus", "ville", "villes",
        "implantation", "sites"
    },

    "admission": {
        "admission", "inscription",
        "candidature", "inscrire",
        "admissions"
    },

    "debouches": {
        "debouche", "debouches",
        "metier", "metiers",
        "carriere", "carrieres"
    },

    "laboratoires": {
        "laboratoire", "laboratoires",
        "recherche", "scientifique",
        "scientifiques", "experimentation"
    },

    "equipements": {
        "equipement", "equipements",
        "materiel", "materiels",
        "installation", "installations",
        "plateforme", "plateformes",
        "simulation", "prototypage"
    }
}


# =====================================================
# CONFIGURATION CPU / GPU
# =====================================================

def get_compute_device() -> str:
    preference = os.getenv(
        "EMSI_AI_DEVICE",
        "auto"
    ).strip().lower()

    if preference == "cpu":
        return "cpu"

    if preference not in ("auto", "cuda"):
        raise ValueError(
            "EMSI_AI_DEVICE doit Ãªtre "
            "'auto', 'cpu' ou 'cuda'."
        )

    if torch.cuda.is_available():
        return "cuda"

    if preference == "cuda":
        raise RuntimeError(
            "CUDA demandÃ©, mais indisponible."
        )

    return "cpu"


# =====================================================
# NORMALISATION DU TEXTE
# =====================================================

def normalize_text(text: str) -> str:
    text = repair_common_mojibake(str(text))
    text = unicodedata.normalize(
        "NFKD",
        text.lower()
    )

    return "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )


def tokenize(text: str) -> set[str]:
    words = re.findall(
        r"[a-z0-9]+",
        normalize_text(text)
    )

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in STOPWORDS
    }


# =====================================================
# SCORE LEXICAL AVEC SYNONYMES
# =====================================================

def keyword_score(
    question: str,
    content: str
) -> float:

    query_words = tokenize(question)
    content_words = tokenize(content)

    if not query_words:
        return 0.0

    matched = 0

    for word in query_words:

        if word in content_words:
            matched += 1
            continue

        for synonyms in SYNONYMS.values():
            if word in synonyms:
                if synonyms.intersection(content_words):
                    matched += 1
                break

    return matched / len(query_words)


# =====================================================
# BONUS POUR LES QUESTIONS SUR LES FORMATIONS
# =====================================================

def topic_bonus(
    question: str,
    content: str
) -> float:

    text = normalize_text(content)

    if not should_apply_program_topic_bonus(question, content):
        return 0.0

    bonus = 0.0

    if re.search(
        r"\bfiliere\s+genie\b",
        text
    ):
        bonus += 0.10

    if re.search(
        r"\bgenie\s+"
        r"(informatique|industriel|electrique|civil|financier)\b",
        text
    ):
        bonus += 0.08

    if "certificats professionnels" in text:
        bonus -= 0.12

    if (
        "temoignages" in text
        or "laureats, recruteurs" in text
    ):
        bonus -= 0.10

    return bonus


# =====================================================
# BONUS DE PERTINENCE LABORATOIRES / Ã‰QUIPEMENTS
# =====================================================


def relevance_bonus(
    question: str,
    content: str
) -> float:

    query = normalize_text(question)
    text = normalize_text(content)

    bonus = 0.0

    asks_laboratories = "laboratoire" in query

    asks_equipment = any(
        word in query
        for word in (
            "equipement",
            "materiel",
            "installation"
        )
    )

    if asks_laboratories:
        if "laboratoire" in text:
            bonus += 0.04

        if "laboratoires modernes" in text:
            bonus += 0.18

        if "smartilab" in text:
            bonus += 0.10

    if asks_equipment:
        if "equipement" in text:
            bonus += 0.10

        if "salles informatiques" in text:
            bonus += 0.10

        if "plateforme" in text:
            bonus += 0.08

        if "simulation" in text:
            bonus += 0.08

        if "prototypage" in text:
            bonus += 0.08

    if asks_laboratories or asks_equipment:
        if (
            "activites sportives" in text
            or "clubs artistiques" in text
        ):
            bonus -= 0.12

    return bonus


# =====================================================
# CHARGEMENT BGE-M3
# =====================================================

@lru_cache(maxsize=1)
def get_embedding_model():

    torch.set_num_threads(
        MAX_CPU_THREADS
    )

    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    device = get_compute_device()

    logger.info(
        "Chargement BGE-M3 sur %s",
        device
    )

    model = SentenceTransformer(
        BGE_MODEL,
        device=device
    )

    model.eval()

    return model


# =====================================================
# DIVERSIFICATION DES DOCUMENTS
# =====================================================

def diversify_documents(
    documents: list[dict],
    limit: int
) -> list[dict]:

    selected = []
    page_counts = {}

    for document in documents:

        page_key = (
            document["source"],
            document["page"]
        )

        count = page_counts.get(
            page_key,
            0
        )

        if count >= MAX_PASSAGES_PER_PAGE:
            continue

        selected.append(document)

        page_counts[page_key] = count + 1

        if len(selected) >= limit:
            break

    return selected


# =====================================================
# RECHERCHE HYBRIDE BGE-M3 + QDRANT
# =====================================================


def search_documents(
    question: str,
    limit: int = 5
) -> list[dict]:

    start_total = time.perf_counter()

    question = str(question).strip()

    if not question:
        return []

    limit = max(1, min(int(limit), 10))

    # 1. Chargement du modÃ¨le BGE-M3
    start_model = time.perf_counter()
    model = get_embedding_model()

    logger.warning(
        "[PERF] Chargement BGE-M3: %.2fs",
        time.perf_counter() - start_model
    )

    # 2. CrÃ©ation de l'embedding
    start_embedding = time.perf_counter()

    try:
        with torch.inference_mode():
            vector = model.encode(
                question,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=1
            )

    except torch.cuda.OutOfMemoryError as exc:
        logger.exception(
            "MÃ©moire GPU insuffisante pour BGE-M3"
        )
        raise RuntimeError(
            "MÃ©moire GPU insuffisante pour BGE-M3."
        ) from exc

    logger.warning(
        "[PERF] Encodage question: %.2fs",
        time.perf_counter() - start_embedding
    )

    # 3. Recherche Qdrant
    start_qdrant = time.perf_counter()

    client = QdrantClient(
        url=QDRANT_URL,
        timeout=20
    )

    candidate_limit = min(
        MAX_CANDIDATES,
        max(limit * 10, 30)
    )
    exhaustive_program_list = is_exhaustive_program_question(question)
    program_duration_query = is_program_duration_question(question)

    results = client.query_points(
        collection_name=TEXT_COLLECTION,
        query=vector.tolist(),
        limit=candidate_limit,
        with_payload=True
    ).points

    supplemental_catalog_points = []
    supplemental_catalog_ids = set()
    if exhaustive_program_list:
        candidate_catalogs = [
            point for point in results
            if program_catalog_bonus(
                question,
                str((point.payload or {}).get("content", "")),
                exhaustive=True,
            ) > 0
        ]
        if not candidate_catalogs:
            # A semantic top-60 can omit a compact summary page even when its
            # detailed course pages rank highly. For list queries only, inspect
            # the small existing payload collection and add matching curriculum
            # structure; this reads no vectors and performs no reindexing.
            scroll_points, next_offset = client.scroll(
                collection_name=TEXT_COLLECTION,
                limit=256,
                with_payload=True,
                with_vectors=False,
            )
            all_points = list(scroll_points)
            while next_offset is not None:
                scroll_points, next_offset = client.scroll(
                    collection_name=TEXT_COLLECTION,
                    limit=256,
                    offset=next_offset,
                    with_payload=True,
                    with_vectors=False,
                )
                if not scroll_points:
                    break
                all_points.extend(scroll_points)

            seen_ids = {str(getattr(point, "id", "")) for point in results}
            supplemental_catalog_points = [
                point for point in all_points
                if str(getattr(point, "id", "")) not in seen_ids
                and program_catalog_bonus(
                    question,
                    str((point.payload or {}).get("content", "")),
                    exhaustive=True,
                ) > 0
            ]
            supplemental_catalog_ids = {
                str(getattr(point, "id", ""))
                for point in supplemental_catalog_points
            }
            results.extend(supplemental_catalog_points)
        logger.info(
            "[RAG_EXHAUSTIVE] qdrant_candidates=%d catalog_candidates=%d supplemental=%d",
            len(results),
            len(candidate_catalogs) + len(supplemental_catalog_points),
            len(supplemental_catalog_points),
        )
    elif program_duration_query:
        # Duration queries are specific, so normal top-k retrieval can miss the
        # compact curriculum summary. Scan only the small existing payload set
        # (no vectors or model work) and add matching structured curriculum chunks.
        scroll_points, next_offset = client.scroll(
            collection_name=TEXT_COLLECTION,
            limit=256,
            with_payload=True,
            with_vectors=False,
        )
        all_points = list(scroll_points)
        while next_offset is not None:
            scroll_points, next_offset = client.scroll(
                collection_name=TEXT_COLLECTION,
                limit=256,
                offset=next_offset,
                with_payload=True,
                with_vectors=False,
            )
            if not scroll_points:
                break
            all_points.extend(scroll_points)

        seen_ids = {str(getattr(point, "id", "")) for point in results}
        supplemental_catalog_points = [
            point for point in all_points
            if str(getattr(point, "id", "")) not in seen_ids
            and program_duration_catalog_bonus(
                question,
                str((point.payload or {}).get("content", "")),
            ) > 0
        ]
        supplemental_catalog_ids = {
            str(getattr(point, "id", "")) for point in supplemental_catalog_points
        }
        results.extend(supplemental_catalog_points)
        logger.info(
            "[RAG_PROGRAM_DURATION] qdrant_candidates=%d supplemental=%d",
            len(results), len(supplemental_catalog_points),
        )

    logger.warning(
        "[PERF] Recherche Qdrant: %.2fs",
        time.perf_counter() - start_qdrant
    )

    # 4. Classement hybride
    start_ranking = time.perf_counter()

    documents = []

    for result in results:
        payload = result.payload or {}
        content = repair_common_mojibake(
            str(payload.get("content", ""))
        ).strip()

        if not content:
            continue

        semantic_score = float(getattr(result, "score", 0.0) or 0.0)

        lexical_score = keyword_score(
            question, content
        )

        contextual_bonus = topic_bonus(
            question, content
        )

        extra_bonus = relevance_bonus(
            question, content
        )

        campus_bonus = campus_list_bonus(
            question, content
        )

        catalog_bonus = program_catalog_bonus(
            question, content, exhaustive=exhaustive_program_list
        )
        duration_catalog_bonus = program_duration_catalog_bonus(
            question, content
        )
        catalog_bonus = max(catalog_bonus, duration_catalog_bonus)
        point_id = str(getattr(result, "id", ""))

        combined_score = (
            SEMANTIC_WEIGHT * semantic_score
            + LEXICAL_WEIGHT * lexical_score
            + contextual_bonus
            + extra_bonus
            + campus_bonus
            + catalog_bonus
        )

        documents.append({
            "id": point_id,
            "chunk_index": payload.get("chunk_index"),
            "content": content,
            "source": payload.get("source", ""),
            "page": payload.get("page", 0),
            "score": round(combined_score, 4),
            "semantic_score": round(semantic_score, 4),
            "lexical_score": round(lexical_score, 4),
            "catalog_bonus": round(catalog_bonus, 4),
            "duration_catalog_bonus": round(duration_catalog_bonus, 4),
            "retrieval_origin": "qdrant_scroll" if point_id in supplemental_catalog_ids else "vector_search",
            "catalog_evidence": catalog_bonus > 0,
        })

    documents.sort(
        key=lambda doc: doc["score"],
        reverse=True
    )

    selected = diversify_documents(documents, limit)
    if exhaustive_program_list or program_duration_query:
        catalog_docs = [
            document for document in documents
            if document.get("catalog_evidence")
            and document["score"] >= 0.20
        ]
        if catalog_docs and not any(item.get("catalog_evidence") for item in selected):
            if len(selected) >= limit:
                selected[-1] = catalog_docs[0]
            else:
                selected.append(catalog_docs[0])
            selected.sort(key=lambda item: item["score"], reverse=True)
        diagnostic_prefix = (
            "[RAG_EXHAUSTIVE]" if exhaustive_program_list
            else "[RAG_PROGRAM_DURATION]"
        )
        logger.info(
            "%s ranked=%s selected=%s",
            diagnostic_prefix,
            [
                {"rank": rank, "id": item["id"], "page": item["page"],
                 "chunk_index": item["chunk_index"], "score": item["score"],
                 "semantic_score": item["semantic_score"],
                 "lexical_score": item["lexical_score"],
                 "catalog_bonus": item["catalog_bonus"],
                 "retrieval_origin": item["retrieval_origin"],
                 "excerpt": item["content"][:180]}
                for rank, item in enumerate(documents, start=1)
            ],
            [
                {"id": item["id"], "page": item["page"],
                 "chunk_index": item["chunk_index"], "score": item["score"],
                 "retrieval_origin": item["retrieval_origin"]}
                for item in selected
            ],
        )

    logger.warning(
        "[PERF] Classement hybride: %.2fs",
        time.perf_counter() - start_ranking
    )

    logger.warning(
        "[PERF] Recherche complÃ¨te: %.2fs",
        time.perf_counter() - start_total
    )

    return selected
