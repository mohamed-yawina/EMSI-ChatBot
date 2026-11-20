
import json
import os
import sys

import torch
from qdrant_client import QdrantClient
from transformers import CLIPModel, CLIPProcessor
from app.rag.image_utils import build_image_result


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

    processor = CLIPProcessor.from_pretrained(
        CLIP_MODEL
    )

    model = None
    inputs = None
    features = None
    vector = None

    try:
        model = CLIPModel.from_pretrained(
            CLIP_MODEL
        ).to(device)

        model.eval()

        inputs = processor(
            text=questions,
            return_tensors="pt",
            padding=True,
            truncation=True
        )

        inputs = {
            key: value.to(device)
            for key, value in inputs.items()
        }

        with torch.inference_mode():
            features = model.get_text_features(
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
            return [row.cpu().tolist() for row in features]

    except torch.cuda.OutOfMemoryError as exc:
        raise RuntimeError(
            "Mémoire GPU insuffisante pour CLIP. "
            "Fermez les applications utilisant la RTX 3050."
        ) from exc

    finally:
        del features, inputs, model

        if device == "cuda":
            torch.cuda.empty_cache()


# =====================================================
# RECHERCHE DES IMAGES DANS QDRANT
# =====================================================

def search_images(question, limit=3, mode="generic"):
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
    query_vectors = encode_questions(query_prompts, device)

    # 2. Rechercher les images similaires.
    client = QdrantClient(
        url=QDRANT_URL,
        timeout=20
    )

    candidate_limit = (
        MAX_CONTRAST_CANDIDATES
        if mode == "brochure"
        else min(60, max(limit * 8, 20))
    )

    results = client.query_points(
        collection_name=IMAGE_COLLECTION,
        query=query_vectors[0],
        limit=candidate_limit,
        with_payload=True
    ).points

    # Contrastive scores compare the requested visual category with likely
    # confounders. Querying the small image collection does not re-encode or
    # alter its vectors; it only scores existing points.
    negative_scores = {}
    for vector in query_vectors[1:]:
        points = client.query_points(
            collection_name=IMAGE_COLLECTION,
            query=vector,
            limit=MAX_CONTRAST_CANDIDATES,
            with_payload=False,
        ).points
        for point in points:
            negative_scores.setdefault(str(point.id), []).append(float(point.score))

    # 3. Préparer les résultats pour Flutter.
    images = []
    used_urls = set()
    used_pages = set()
    diagnostics = LAST_DIAGNOSTICS

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

    return images


# =====================================================
# EXÉCUTION ISOLÉE
# =====================================================

def main():
    try:
        raw_request = sys.stdin.read()

        request = json.loads(raw_request)

        question = request.get(
            "question", ""
        )

        limit = request.get(
            "limit", 3
        )
        mode = request.get("mode", "generic")

        images = search_images(
            question,
            limit,
            mode,
        )

        if LAST_DIAGNOSTICS:
            print(
                "CLIP candidats (score/marge/decision): "
                + json.dumps(LAST_DIAGNOSTICS[:60], ensure_ascii=False),
                file=sys.stderr,
                flush=True,
            )

        # Important :
        # stdout doit contenir uniquement du JSON.
        print(
            json.dumps(
                {"images": images},
                ensure_ascii=False
            ),
            flush=True
        )

    except Exception as exc:
        print(
            f"Erreur CLIP : {exc}",
            file=sys.stderr,
            flush=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
