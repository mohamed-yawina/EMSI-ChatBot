
import json
import sys
from pathlib import Path

import pymupdf


BASE_DIR = Path(__file__).resolve().parents[2]
INPUT_DIR = BASE_DIR / "data" / "documents"
OUTPUT_DIR = BASE_DIR / "data" / "processed"


def extract_pdf(pdf_path: Path):
    document_dir = OUTPUT_DIR / pdf_path.stem
    images_dir = document_dir / "images"

    images_dir.mkdir(parents=True, exist_ok=True)

    results = []

    with pymupdf.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            page_number = page_index + 1

            # Extraction du texte
            text = page.get_text("text").strip()

            if text:
                results.append({
                    "type": "text",
                    "source": pdf_path.name,
                    "page": page_number,
                    "content": text
                })

            # Extraction des images intégrées
            for image_index, image_info in enumerate(
                page.get_images(full=True), start=1
            ):
                xref = image_info[0]
                image_data = doc.extract_image(xref)

                extension = image_data["ext"]
                image_name = (
                    f"page_{page_number}_image_{image_index}"
                    f".{extension}"
                )

                image_path = images_dir / image_name
                image_path.write_bytes(image_data["image"])

                results.append({
                    "type": "image",
                    "source": pdf_path.name,
                    "page": page_number,
                    "path": str(image_path.relative_to(BASE_DIR))
                })

            # Extraction des tableaux
            tables = page.find_tables()

            for table_index, table in enumerate(tables.tables, 1):
                results.append({
                    "type": "table",
                    "source": pdf_path.name,
                    "page": page_number,
                    "table_index": table_index,
                    "content": table.extract()
                })

            print(f"Page {page_number} extraite")

    output_file = document_dir / "extracted.json"

    output_file.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\nExtraction terminée : {output_file}")
    print(f"Éléments extraits : {len(results)}")


if __name__ == "__main__":
    INPUT_DIR.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(INPUT_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"Aucun PDF trouvé dans : {INPUT_DIR}")
        sys.exit(1)

    for pdf_file in pdf_files:
        print(f"\nTraitement : {pdf_file.name}")
        extract_pdf(pdf_file)
