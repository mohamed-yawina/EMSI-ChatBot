
import json
import os
import sys
import time

_WORKER_IMPORT_STARTED = time.perf_counter()

import torch
from qdrant_client import QdrantClient
from transformers import CLIPModel, CLIPProcessor
from app.rag.image_utils import build_image_result


def _perf(stage, started, **details):
    """Emit bounded, secret-free worker timings on stderr for parent capture."""
    record = {
        "stage": stage,
        "seconds": round(time.perf_counter() - started, 3),
        **details,
    }
    print("[CLIP_PERF] " + json.dumps(record, ensure_ascii=True), file=sys.stderr, flush=True)


_perf("worker_imports", _WORKER_IMPORT_STARTED)


# =====================================================
# CONFIGURATION
# =====================================================

QDRANT_URL = os.getenv("EMSI_QDRANT_URL", "http://127.0.0.1:6333")
IMAGE_COLLECTION = "emsi_images"
CLIP_MODEL = "openai/clip-vit-base-patch32"

MAX_CPU_THREADS = 2
MAX_RESULTS = 10
MAX_CONTRAST_CANDIDATES = 200
LAST_DIAGNOSTICS = []
_PROCESSOR = None
_MODEL = None
_QDRANT_CLIENT = None

NEGATIVE_PROMPTS = {
    "generic": (
        "a decorative infographic, logo, or abstract brochure graphic",
        "a text-only page or typography without a documentary visual",
    ),
    "campus": (
        "a graduation ceremony with people wearing caps and gowns",
        "a decorative infographic, logo, or abstract brochure graphic",
    ),
    "laboratory": (
        "a graduation ceremony with people wearing caps and gowns",
        "the exterior of a university campus building",
        "a decorative infographic, logo, or abstract brochure graphic",
    ),
    "event": (
        "the exterior of a university campus building",
        "a university research laboratory with scientific equipment",
        "a decorative infographic, logo, or abstract brochure graphic",
    ),
}


def _mode_prompt(question, mode):
    if mode == "campus":
        return "A real documentary photograph of an EMSI university campus building or campus grounds. " + question
    if mode == "laboratory":
        return "A real documentary photograph of an EMSI teaching or research laboratory with equipment. " + question
    if mode == "event":
        return "A real documentary photograph of the specific EMSI academic event requested. " + question
    if mode == "brochure":
        return "A representative non-decorative photograph or substantive illustration extracted from the EMSI brochure."
    return question

# =====================================================
# ENCODAGE DE LA QUESTION AVEC CLIP
# =====================================================

def encode_questions(questions, device):
    global _PROCESSOR, _MODEL
    torch.set_num_threads(MAX_CPU_THREADS)

    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass

    print(
        f"CLIP utilise : {device}",
        file=sys.stderr,
        flush=True
    )

    if _PROCESSOR is None:
        processor_started = time.perf_counter()
        _PROCESSOR = CLIPProcessor.from_pretrained(CLIP_MODEL)
        _perf("processor_load", processor_started)
    if _MODEL is None:
        model_started = time.perf_counter()
        _MODEL = CLIPModel.from_pretrained(CLIP_MODEL).to(device)
        _MODEL.eval()
        _perf("model_load", model_started, device=device)

    inputs = None
    features = None

    try:
        inputs = _PROCESSOR(
            text=questions,
            return_tensors="pt",
            padding=True,
            truncation=True
        )

        inputs = {
            key: value.to(device)
            for key, value in inputs.items()
        }

        embedding_started = time.perf_counter()
        with torch.inference_mode():
            features = _MODEL.get_text_features(
                **inputs
            )

            # Compatibilité avec différentes versions
            # de Transformers.
            if not isinstance(features, torch.Tensor):
                if getattr(features, "pooler_output", None) is not None:
                    features = features.pooler_output
                elif getattr(features, "text_embeds", None) is not None:
                    features = features.text_embeds
                else:
                    raise TypeError(
                        "Format de sortie CLIP non reconnu."
                    )

            features = features.float()
            features = features / features.norm(dim=-1, keepdim=True).clamp(min=1e-12)
            _perf("text_embeddings", embedding_started, prompts=len(questions), device=device)
            return [row.cpu().tolist() for row in features]

    except torch.cuda.OutOfMemoryError as exc:
        raise RuntimeError(
            "Mémoire GPU insuffisante pour CLIP. "
            "Fermez les applications utilisant la RTX 3050."
        ) from exc

    finally:
        del features, inputs

        if device == "cuda":
            torch.cuda.empty_cache()


# =====================================================
# RECHERCHE DES IMAGES DANS QDRANT
# =====================================================

def search_images(question, limit=3, mode="generic"):
    global _QDRANT_CLIENT
    global LAST_DIAGNOSTICS
    LAST_DIAGNOSTICS = []
    question = str(question).strip()

    if not question:
        return []

    limit = max(1, min(int(limit), MAX_RESULTS))

    # API image searches are deliberately CPU-only for memory stability.
    device = "cpu"

    positive_prompt = _mode_prompt(question, mode)
    negative_prompts = NEGATIVE_PROMPTS.get(mode, ())
    query_prompts = [positive_prompt, *negative_prompts]
    embedding_started = time.perf_counter()
    query_vectors = encode_questions(query_prompts, device)
    _perf("encode_questions_total", embedding_started, prompts=len(query_prompts))

    # 2. Rechercher les images similaires.
    if _QDRANT_CLIENT is None:
        qdrant_client_started = time.perf_counter()
        _QDRANT_CLIENT = QdrantClient(url=QDRANT_URL, timeout=20)
        _perf("qdrant_client_init", qdrant_client_started)
    client = _QDRANT_CLIENT

    candidate_limit = (
        MAX_CONTRAST_CANDIDATES
        if mode == "brochure"
        else min(60, max(limit * 8, 20))
    )

    positive_query_started = time.perf_counter()
    results = client.query_points(
        collection_name=IMAGE_COLLECTION,
        query=query_vectors[0],
        limit=candidate_limit,
        with_payload=True
    ).points
    _perf("qdrant_positive_query", positive_query_started, candidates=len(results))

    # Contrastive scores compare the requested visual category with likely
    # confounders. Querying the small image collection does not re-encode or
    # alter its vectors; it only scores existing points.
    negative_scores = {}
    negative_query_started = time.perf_counter()
    for vector in query_vectors[1:]:
        points = client.query_points(
            collection_name=IMAGE_COLLECTION,
            query=vector,
            limit=MAX_CONTRAST_CANDIDATES,
            with_payload=False,
        ).points
        for point in points:
            negative_scores.setdefault(str(point.id), []).append(float(point.score))
    _perf("qdrant_contrast_queries", negative_query_started,
          prompts=len(query_vectors) - 1, ids_scored=len(negative_scores))

    # 3. Préparer les résultats pour Flutter.
    images = []
    used_urls = set()
    used_pages = set()
    diagnostics = LAST_DIAGNOSTICS
    filtering_started = time.perf_counter()

    for result in results:
        payload = result.payload or {}

        image = build_image_result(
            payload,
            result.score,
            result.id,
        )
        if not image:
            diagnostics.append({
                "id": str(result.id),
                "page": (result.payload or {}).get("page"),
                "score": round(float(result.score), 4),
                "decision": "rejected_asset_quality_or_metadata",
            })
            continue
        page_key = str(image.get("page"))
        if page_key in used_pages:
            diagnostics.append({
                "id": str(result.id), "page": page_key,
                "score": round(float(result.score), 4),
                "decision": "rejected_duplicate_page",
            })
            continue

        image_id = str(result.id)
        if negative_prompts:
            scores = negative_scores.get(image_id)
            # Missing contrast scores mean the visual class was not verified.
            if not scores or len(scores) != len(negative_prompts):
                diagnostics.append({
                    "id": image_id, "page": image.get("page"),
                    "score": round(float(result.score), 4),
                    "decision": "rejected_contrast_scores_missing",
                })
                continue
            image["visual_margin"] = round(float(result.score) - max(scores), 4)
            diagnostics.append({
                "id": image_id, "page": image.get("page"),
                "score": image["score"], "visual_margin": image["visual_margin"],
                "decision": "passed_to_page_evidence_filter",
            })

        image_url = image["url"]
        if image_url in used_urls:
            continue

        used_urls.add(image_url)
        used_pages.add(page_key)

        images.append(image)

        # Keep image galleries diverse and avoid showing several crops from a
        # single brochure page as if they were separate subjects.
        if len(used_pages) >= limit:
            break

    _perf("candidate_filtering", filtering_started,
          candidates=len(results), retained=len(images), decisions=len(diagnostics))
    return images


# =====================================================
# EXÉCUTION ISOLÉE
# =====================================================

def main():
    try:
        for raw_request in sys.stdin:
            if not raw_request.strip():
                continue
            try:
                request = json.loads(raw_request)
                if request.get("command") == "shutdown":
                    print(json.dumps({"shutdown": True}), flush=True)
                    return

                worker_started = time.perf_counter()
                images = search_images(
                    request.get("question", ""),
                    request.get("limit", 3),
                    request.get("mode", "generic"),
                )
                _perf("worker_total", worker_started, retained=len(images))
                if LAST_DIAGNOSTICS:
                    print(
                        "CLIP candidats (score/marge/decision): "
                        + json.dumps(LAST_DIAGNOSTICS[:60], ensure_ascii=True),
                        file=sys.stderr,
                        flush=True,
                    )
                print(json.dumps({"images": images}, ensure_ascii=False), flush=True)
            except Exception as exc:
                print(f"Erreur CLIP : {exc}", file=sys.stderr, flush=True)
                print(json.dumps({"error": "clip_search_failed"}), flush=True)
    except Exception as exc:
        print(f"Erreur CLIP worker : {exc}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
