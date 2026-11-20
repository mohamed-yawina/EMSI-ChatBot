"""Lightweight helpers for validating indexed image paths and metadata."""
from pathlib import Path
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MIN_SEARCH_IMAGE_BYTES = 16 * 1024
MIN_IMAGE_SIDE_PX = 160
MIN_IMAGE_AREA_PX = 100_000


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
    # PDF extraction leaves tiny transparent glyphs/icons in Qdrant. They are
    # valid files but useless as chat photos, so do not return them as results.
    try:
        if image_path.stat().st_size < MIN_SEARCH_IMAGE_BYTES:
            return None
    except OSError:
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

    try:
        with Image.open(Path(processed_dir) / Path(image_url.removeprefix("/images/"))) as asset:
            width, height = asset.size
    except (OSError, ValueError):
        return None
    if min(width, height) < MIN_IMAGE_SIDE_PX or width * height < MIN_IMAGE_AREA_PX:
        return None
    aspect_ratio = max(width, height) / min(width, height)
    if aspect_ratio > 3.2:
        return None

    image = {
        "id": str(payload.get("id", result_id)),
        "url": image_url,
        "filename": Path(image_url).name,
        "source": source.strip(),
        "page": int(page),
        "score": numeric_score,
        "width": int(width),
        "height": int(height),
        "aspect_ratio": round(aspect_ratio, 3),
    }
    # A caption must be explicitly marked as documentary/verified. Page text
    # and generated descriptions are context, never image captions.
    caption = payload.get("caption")
    if payload.get("caption_verified") is True and isinstance(caption, str) and caption.strip():
        image["caption"] = caption.strip()[:500]
        image["caption_verified"] = True
    return image
