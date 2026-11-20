"""Compose readiness check: API process plus required Qdrant collections."""

import json
import os
import sys
from urllib.request import urlopen


def main() -> int:
    qdrant_url = os.getenv("EMSI_QDRANT_URL", "http://qdrant:6333").rstrip("/")
    try:
        with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            if response.status != 200:
                return 1
        with urlopen(f"{qdrant_url}/collections", timeout=2) as response:
            collections = json.load(response).get("result", {}).get("collections", [])
    except Exception:
        return 1

    names = {item.get("name") for item in collections}
    return 0 if {"emsi_text", "emsi_images"}.issubset(names) else 1


if __name__ == "__main__":
    sys.exit(main())
