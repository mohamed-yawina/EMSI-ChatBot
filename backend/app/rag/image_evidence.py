"""Lightweight same-page text evidence for indexed brochure images."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from app.rag.image_utils import PROJECT_ROOT


CHUNKS_PATH = PROJECT_ROOT / "data" / "processed" / "Brochure-EMSI" / "chunks.json"
DEFAULT_MIN_CLIP_SCORE = 0.20
_STOP_WORDS = {
    "a", "au", "aux", "avec", "dans", "de", "des", "du", "elle", "et",
    "la", "le", "les", "ma", "mes", "mon", "moi", "nous", "par", "pour",
    "sa", "son", "ses", "sur", "un", "une", "vous", "photo", "photos",
    "image", "images", "montre", "donne", "brochure", "emsi", "presente",
    "presentees", "presente", "retrouvee", "retrouvees", "dun", "dune",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(char for char in value if not unicodedata.combining(char))


@lru_cache(maxsize=1)
def _load_chunks() -> tuple[dict, ...]:
    try:
        payload = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, list):
        return ()
    return tuple(item for item in payload if isinstance(item, dict))


def page_context(source: str, page: int | str, query: str = "") -> str:
    """Return an extractive passage from the same brochure page, if present."""
    try:
        page_number = int(page)
    except (TypeError, ValueError):
        return ""
    chunks = [
        item for item in _load_chunks()
        if str(item.get("source", "")).casefold() == str(source).casefold()
        and str(item.get("page", "")) == str(page_number)
        and isinstance(item.get("content"), str)
    ]
    if not chunks:
        return ""
    chunks.sort(key=lambda item: int(item.get("chunk_index", 0) or 0))
    terms = [
        token for token in re.findall(r"[a-z0-9]{3,}", _normalize(query))
        if token not in _STOP_WORDS
    ]
    ranked = sorted(
        chunks,
        key=lambda item: sum(
            term in _normalize(item.get("content", "")) for term in terms
        ),
        reverse=True,
    )
    text = " ".join(str(item.get("content", "")).strip() for item in ranked[:2])
    return re.sub(r"\s+", " ", text).strip()[:700]


def minimum_clip_score() -> float:
    """Read an adjustable threshold without making HTTP input control filtering."""
    try:
        value = float(os.getenv("EMSI_CLIP_MIN_SCORE", str(DEFAULT_MIN_CLIP_SCORE)))
    except (TypeError, ValueError):
        return DEFAULT_MIN_CLIP_SCORE
    return min(max(value, -1.0), 1.0)


def image_candidate_evidence(
    image: dict,
    intent,
    selected_documents: list[dict],
) -> tuple[bool, str]:
    relevant, context, _ = image_candidate_decision(image, intent, selected_documents)
    return relevant, context


def image_candidate_decision(
    image: dict,
    intent,
    selected_documents: list[dict],
) -> tuple[bool, str, str]:
    """Require visual CLIP evidence; page text is corroboration, not image proof."""
    try:
        score = float(image.get("score"))
    except (TypeError, ValueError):
        return False, "", "score_missing"

    source = str(image.get("source", ""))
    page = str(image.get("page", ""))
    context = page_context(source, page, intent.query)
    # A document-wide request asks for a representative sample, not a visual
    # match to the literal word "brochure". The worker has already validated
    # that each candidate is a readable asset from the indexed brochure.
    if intent.mode == "brochure":
        return True, context, "brochure_sample_ranked_by_clip"

    if score < minimum_clip_score():
        return False, context, "below_existing_clip_floor"
    if not context:
        return False, context, "same_page_text_missing"

    normalized_context = _normalize(context)
    if intent.mode == "campus":
        topical_match = bool(re.search(r"\b(campus|implantation|site)\b", normalized_context))
    elif intent.mode == "laboratory":
        topical_match = bool(re.search(r"\b(laboratoire|labo|atelier|travaux pratiques|plateforme)\b", normalized_context))
    elif intent.mode == "event":
        topical_match = bool(re.search(r"\b(evenement|conference|ceremonie|diplomes?|forum|journee)\b", normalized_context))
    elif intent.mode == "person":
        # Person matching is handled by the stricter caption + text guard.
        return False, context, "person_requires_explicit_caption"
    else:
        terms = [
            token for token in re.findall(r"[a-z0-9]{3,}", _normalize(intent.query))
            if token not in _STOP_WORDS
        ]
        topical_match = bool(terms) and any(term in normalized_context for term in terms)

    # Text from the page alone cannot prove what an image depicts. Require the
    # requested visual class to outrank confounding CLIP prompts.
    try:
        visual_margin = float(image.get("visual_margin"))
    except (TypeError, ValueError):
        return False, context, "contrast_scores_missing"
    if visual_margin <= 0:
        return False, context, "confounder_prompt_scored_at_least_as_high"
    if not topical_match:
        return False, context, "page_context_not_topical"
    return True, context, "positive_contrast_and_topical_page_context"


def select_diverse_images(images: list[dict], limit: int = 3) -> list[dict]:
    """Keep the highest-ranked valid image per source page."""
    selected = []
    seen_pages = set()
    seen_urls = set()
    for image in images:
        source = str(image.get("source", "")).casefold()
        page = str(image.get("page", ""))
        url = str(image.get("url", ""))
        if not source or not page or not url:
            continue
        page_key = (source, page)
        if page_key in seen_pages or url in seen_urls:
            continue
        selected.append(image)
        seen_pages.add(page_key)
        seen_urls.add(url)
        if len(selected) >= max(1, limit):
            break
    return selected
