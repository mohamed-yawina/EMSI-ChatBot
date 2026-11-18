
import json
import uuid
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "processed" / "Brochure-EMSI"

QDRANT_URL = "http://localhost:6333"

TEXT_COLLECTION = "emsi_text"
IMAGE_COLLECTION = "emsi_images"


def load_json(filename):
    with (DATA_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


def load_embeddings(filename):
    with np.load(DATA_DIR / filename, allow_pickle=False) as data:
        vectors = data["embeddings"].astype(np.float32)
        ids = data["ids"].astype(str).tolist()

    if vectors.ndim != 2:
        raise ValueError(f"Vecteurs invalides : {filename}")

    if len(ids) != len(vectors):
        raise ValueError(f"IDs et vecteurs non alignés : {filename}")

    if not np.isfinite(vectors).all():
        raise ValueError(f"NaN ou inf détecté : {filename}")

    return ids, vectors


def ensure_collection(client, name, dimensions):
    if client.collection_exists(name):
        info = client.get_collection(name)
        existing_size = info.config.params.vectors.size

        if existing_size != dimensions:
            raise ValueError(
                f"{name} utilise {existing_size} dimensions, "
                f"mais {dimensions} sont attendues."
            )

        print(f"Collection existante : {name}")
    else:
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=dimensions,
                distance=models.Distance.COSINE
            )
        )

        print(f"Collection créée : {name}")


def index_vectors(client, collection, ids, vectors, metadata):
    metadata_by_id = {
        item["id"]: item
        for item in metadata
    }

    points = []

    for item_id, vector in zip(ids, vectors):
        if item_id not in metadata_by_id:
            raise ValueError(f"Métadonnées absentes : {item_id}")

        payload = metadata_by_id[item_id]

        # Qdrant accepte les UUID comme identifiants.
        point_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{collection}:{item_id}"
            )
        )

        points.append(
            models.PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload={
                    **payload,
                    "original_id": item_id
                }
            )
        )

    for start in range(0, len(points), 32):
        batch = points[start:start + 32]

        client.upsert(
            collection_name=collection,
            points=batch,
            wait=True
        )

    print(f"{len(points)} vecteurs indexés dans {collection}")


def main():
    client = QdrantClient(url=QDRANT_URL, timeout=60)

    # Indexation des textes
    text_metadata = load_json("chunks.json")
    text_ids, text_vectors = load_embeddings("text_embeddings.npz")

    ensure_collection(
        client,
        TEXT_COLLECTION,
        text_vectors.shape[1]
    )

    index_vectors(
        client,
        TEXT_COLLECTION,
        text_ids,
        text_vectors,
        text_metadata
    )

    # Indexation des images
    image_metadata = load_json("image_metadata.json")
    image_ids, image_vectors = load_embeddings("image_embeddings.npz")

    ensure_collection(
        client,
        IMAGE_COLLECTION,
        image_vectors.shape[1]
    )

    index_vectors(
        client,
        IMAGE_COLLECTION,
        image_ids,
        image_vectors,
        image_metadata
    )

    print("\nIndexation multimodale terminée !")

    for name in [TEXT_COLLECTION, IMAGE_COLLECTION]:
        count = client.count(
            collection_name=name,
            exact=True
        ).count

        print(f"{name} : {count} points")


if __name__ == "__main__":
    main()
