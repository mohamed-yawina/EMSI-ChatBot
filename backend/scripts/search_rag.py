
import sys

import numpy as np
import torch
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor


QDRANT_URL = "http://localhost:6333"

TEXT_COLLECTION = "emsi_text"
IMAGE_COLLECTION = "emsi_images"

BGE_MODEL = "BAAI/bge-m3"
CLIP_MODEL = "openai/clip-vit-base-patch32"

TOP_K = 10
RRF_K = 60


def normalize(vector):
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector / max(norm, 1e-12)


def rrf_fusion(text_results, image_results):
    scores = {}
    items = {}

    for collection, result_list in [
        (TEXT_COLLECTION, text_results),
        (IMAGE_COLLECTION, image_results),
    ]:
        for rank, result in enumerate(result_list, start=1):
            key = f"{collection}:{result.id}"

            scores[key] = (
                scores.get(key, 0.0)
                + 1.0 / (RRF_K + rank)
            )

            items[key] = result

    ranked_ids = sorted(
        scores,
        key=lambda key: scores[key],
        reverse=True
    )

    return [
        {
            "score": scores[key],
            "payload": items[key].payload or {}
        }
        for key in ranked_ids
    ]


def main():
    question = " ".join(sys.argv[1:]).strip()

    if not question:
        question = input("Question : ").strip()

    if not question:
        raise ValueError("La question est vide.")

    client = QdrantClient(
        url=QDRANT_URL,
        timeout=60
    )

    # 1. Recherche textuelle BGE-M3
    print("\nChargement de BGE-M3...")

    bge = SentenceTransformer(
        BGE_MODEL,
        device="cpu"
    )

    text_vector = bge.encode(
        question,
        normalize_embeddings=True
    )

    print("Recherche dans emsi_text...")

    text_results = client.query_points(
        collection_name=TEXT_COLLECTION,
        query=text_vector.tolist(),
        limit=TOP_K,
        with_payload=True
    ).points

    # 2. Recherche d'images CLIP
    print("\nChargement de CLIP...")

    processor = CLIPProcessor.from_pretrained(
        CLIP_MODEL
    )

    clip = CLIPModel.from_pretrained(
        CLIP_MODEL
    )

    clip.eval()

    inputs = processor(
        text=[question],
        return_tensors="pt",
        padding=True,
        truncation=True
    )

    with torch.inference_mode():
        features = clip.get_text_features(**inputs)

    if hasattr(features, "pooler_output"):
        features = features.pooler_output

    image_vector = normalize(
        features[0].detach().cpu().numpy()
    )

    print("Recherche dans emsi_images...")

    image_results = client.query_points(
        collection_name=IMAGE_COLLECTION,
        query=image_vector.tolist(),
        limit=TOP_K,
        with_payload=True
    ).points

    # 3. Fusion RRF
    fused_results = rrf_fusion(
        text_results,
        image_results
    )

    # 4. Détecter les demandes d'images
    image_keywords = [
        "image",
        "photo",
        "illustration",
        "montre",
        "voir",
        "visuel"
    ]

    wants_images = any(
        keyword in question.lower()
        for keyword in image_keywords
    )

    # 5. Prioriser selon le type de question
    text_results_ranked = [
        result for result in fused_results
        if result["payload"].get("type") == "text"
    ]

    image_results_ranked = [
        result for result in fused_results
        if result["payload"].get("type") == "image"
    ]

    if wants_images:
        fused_results = (
            image_results_ranked + text_results_ranked
        )
    else:
        fused_results = (
            text_results_ranked + image_results_ranked
        )

    # 6. Affichage des résultats
    print("\n========== RÉSULTATS RAG ==========")
    print("Question :", question)

    for rank, result in enumerate(
        fused_results[:TOP_K],
        start=1
    ):
        payload = result["payload"]

        print(f"\n--- Résultat {rank} ---")
        print("Score RRF :", round(result["score"], 6))
        print("Type :", payload.get("type"))
        print("Source :", payload.get("source"))
        print("Page :", payload.get("page"))

        if payload.get("type") == "text":
            print(
                "Contenu :",
                payload.get("content", "")[:500]
            )
        else:
            print("Image :", payload.get("path"))


if __name__ == "__main__":
    main()
