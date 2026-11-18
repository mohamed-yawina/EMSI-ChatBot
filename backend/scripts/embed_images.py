
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, UnidentifiedImageError
from transformers import CLIPModel, CLIPProcessor


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "processed" / "Brochure-EMSI"

INPUT_FILE = DATA_DIR / "extracted.json"
OUTPUT_FILE = DATA_DIR / "image_embeddings.npz"
METADATA_FILE = DATA_DIR / "image_metadata.json"

MODEL_NAME = "openai/clip-vit-base-patch32"


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        elements = json.load(f)

    images = [item for item in elements if item["type"] == "image"]

    print("Nombre d'images trouvées :", len(images))
    print("Chargement de CLIP :", MODEL_NAME)

    processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    model = CLIPModel.from_pretrained(MODEL_NAME)
    model.eval()

    vectors = []
    metadata = []

    for index, item in enumerate(images, start=1):
        image_path = BASE_DIR / item["path"]

        try:
            with Image.open(image_path) as img:
                image = img.convert("RGB")

            inputs = processor(
                images=image,
                return_tensors="pt"
            )

            with torch.inference_mode():
                features = model.get_image_features(**inputs)

            # Compatibilité avec différentes versions de Transformers
            if hasattr(features, "pooler_output"):
                features = features.pooler_output

            vector = features[0].detach().cpu().numpy()
            vector = vector / max(np.linalg.norm(vector), 1e-12)

            vectors.append(vector.astype(np.float32))

            metadata.append({
                "id": f"image_{index}",
                "source": item["source"],
                "page": item["page"],
                "type": "image",
                "path": item["path"]
            })

            print(f"[{index}/{len(images)}] OK : {image_path.name}")

        except (OSError, ValueError, UnidentifiedImageError) as error:
            print(f"[{index}/{len(images)}] Image ignorée : {error}")

    if not vectors:
        raise RuntimeError("Aucune image n'a pu être encodée.")

    embeddings = np.stack(vectors)

    np.savez_compressed(
        OUTPUT_FILE,
        embeddings=embeddings,
        ids=np.array([item["id"] for item in metadata])
    )

    METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\nEmbeddings images générés !")
    print("Nombre de vecteurs :", embeddings.shape[0])
    print("Dimensions :", embeddings.shape[1])
    print("Fichier :", OUTPUT_FILE)


if __name__ == "__main__":
    main()
