"""Lightweight helpers for validating indexed image paths and metadata."""
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


def build_image_url(path_value, project_root=PROJECT_ROOT, processed_dir=PROCESSED_DIR):
    if not path_value:
        return None

    root = Path(processed_dir).resolve()
    normalized_path = str(path_value).replace("\\", "/")
    image_path = Path(normalized_path)
    if not image_path.is_absolute():
        image_path = Path(project_root) / image_path
    image_path = image_path.resolve()

    try:
        relative_path = image_path.relative_to(root)
    except ValueError:
        return None

    if not image_path.is_file():
        return None
    return "/images/" + relative_path.as_posix()


def build_image_result(payload, score, result_id, project_root=PROJECT_ROOT, processed_dir=PROCESSED_DIR):
    """Build the Flutter contract only from a valid indexed payload and local file."""
    image_url = build_image_url(payload.get("path"), project_root, processed_dir)
    source = payload.get("source")
    page = payload.get("page")
    if not image_url or not isinstance(source, str) or not source.strip():
        return None
    if isinstance(page, bool) or not isinstance(page, (int, str)):
        return None
    if not str(page).strip().isdigit() or int(page) < 1:
        return None

    try:
        numeric_score = round(float(score), 4)
    except (TypeError, ValueError):
        return None

    return {
        "id": str(payload.get("id", result_id)),
        "url": image_url,
        "filename": Path(image_url).name,
        "source": source.strip(),
        "page": int(page),
        "score": numeric_score,
    }
