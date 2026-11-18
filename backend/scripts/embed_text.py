
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parents[2]

DATA_DIR = BASE_DIR / "data" / "processed" / "Brochure-EMSI"

INPUT_FILE = DATA_DIR / "chunks.json"
OUTPUT_FILE = DATA_DIR / "text_embeddings.npz"

MODEL_NAME = "BAAI/bge-m3"


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    texts = [chunk["content"] for chunk in chunks]

    if not texts:
        raise ValueError("Aucun chunk à encoder")

    print(f"Chargement du modèle : {MODEL_NAME}")

    model = SentenceTransformer(MODEL_NAME, device="cpu")

    print(f"Encodage de {len(texts)} chunks...")

    embeddings = model.encode(
        texts,
        batch_size=4,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True
    )

    embeddings = embeddings.astype(np.float32)

    np.savez_compressed(
        OUTPUT_FILE,
        embeddings=embeddings,
        ids=np.array([chunk["id"] for chunk in chunks])
    )

    print("\nEmbeddings générés avec succès")
    print("Nombre de vecteurs :", embeddings.shape[0])
    print("Dimensions :", embeddings.shape[1])
    print("Fichier :", OUTPUT_FILE)

    print("\nNorme du premier vecteur :")
    print(np.linalg.norm(embeddings[0]))


if __name__ == "__main__":
    main()
