
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "Brochure-EMSI"
    / "extracted.json"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "Brochure-EMSI"
    / "chunks.json"
)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def normalize_text(text):
    return re.sub(r"\s+", " ", text).strip()


def split_text(text, size=800, overlap=150):
    if not 0 <= overlap < size:
        raise ValueError("Overlap doit être inférieur au chunk size")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))

        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + size // 2:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = max(start + 1, end - overlap)

    return chunks


def main():
    with INPUT_FILE.open("r", encoding="utf-8") as f:
        elements = json.load(f)

    results = []

    for element in elements:
        if element["type"] != "text":
            continue

        text = normalize_text(element["content"])

        for index, chunk in enumerate(split_text(text)):
            results.append({
                "id": f"{Path(element['source']).stem}_p{element['page']}_c{index}",
                "source": element["source"],
                "page": element["page"],
                "type": "text",
                "chunk_index": index,
                "content": chunk
            })

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Chunking terminé")
    print("Nombre de chunks :", len(results))
    print("Fichier :", OUTPUT_FILE)

    if results:
        print("\nPremier chunk :")
        print(results[0]["content"])


if __name__ == "__main__":
    main()
