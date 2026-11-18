
import json
import sys

import torch
from qdrant_client import QdrantClient
from transformers import CLIPModel, CLIPProcessor
from app.rag.image_utils import build_image_result


# =====================================================
# CONFIGURATION
# =====================================================

QDRANT_URL = "http://127.0.0.1:6333"
IMAGE_COLLECTION = "emsi_images"
CLIP_MODEL = "openai/clip-vit-base-patch32"

MAX_CPU_THREADS = 2
MAX_RESULTS = 10

# =====================================================
# ENCODAGE DE LA QUESTION AVEC CLIP
# =====================================================

def encode_question(question, device):
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
            text=[question],
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

            vector = features[0].float()

            vector = vector / vector.norm().clamp(
                min=1e-12
            )

            # Qdrant attend une liste Python.
            image_vector = vector.cpu().tolist()

        return image_vector

    except torch.cuda.OutOfMemoryError as exc:
        raise RuntimeError(
            "Mémoire GPU insuffisante pour CLIP. "
            "Fermez les applications utilisant la RTX 3050."
        ) from exc

    finally:
        del vector, features, inputs, model

        if device == "cuda":
            torch.cuda.empty_cache()


# =====================================================
# RECHERCHE DES IMAGES DANS QDRANT
# =====================================================

def search_images(question, limit=3):
    question = str(question).strip()

    if not question:
        return []

    limit = max(1, min(int(limit), MAX_RESULTS))

    # API image searches are deliberately CPU-only for memory stability.
    device = "cpu"

    # 1. Encoder la question sur GPU ou CPU.
    image_vector = encode_question(
        question,
        device
    )

    # 2. Rechercher les images similaires.
    client = QdrantClient(
        url=QDRANT_URL,
        timeout=20
    )

    candidate_limit = min(
        30,
        max(limit * 5, 10)
    )

    results = client.query_points(
        collection_name=IMAGE_COLLECTION,
        query=image_vector,
        limit=candidate_limit,
        with_payload=True
    ).points

    # 3. Préparer les résultats pour Flutter.
    images = []
    used_urls = set()

    for result in results:
        payload = result.payload or {}

        image = build_image_result(
            payload,
            result.score,
            result.id,
        )
        if not image:
            continue

        image_url = image["url"]
        if image_url in used_urls:
            continue

        used_urls.add(image_url)

        images.append(image)

        if len(images) >= limit:
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

        images = search_images(
            question,
            limit
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
