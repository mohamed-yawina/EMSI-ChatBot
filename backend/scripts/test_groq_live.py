"""Small live Groq check using simulated EMSI passages; loads no local models."""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

# Fix the requested model for this diagnostic without displaying credentials.
MODEL = "openai/gpt-oss-20b"
os.environ["GROQ_MODEL"] = MODEL

# The Groq service lives under backend/app; no FastAPI or RAG modules are imported.
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.services.groq_service import GroqAPIError, generate_answer


QUESTION = "Quels campus EMSI sont mentionnés dans les documents ?"
DOCUMENTS = [
    {
        "source": "Brochure EMSI",
        "page": 4,
        "content": "Le campus EMSI de Casablanca propose plusieurs formations.",
    },
    {
        "source": "Brochure EMSI",
        "page": 8,
        "content": "Le campus EMSI de Rabat accueille également des étudiants.",
    },
]


def main() -> None:
    if not os.getenv("GROQ_API_KEY", "").strip():
        raise SystemExit("GROQ_API_KEY n'est pas configurée dans l'environnement ou le fichier .env.")

    started = time.perf_counter()
    try:
        answer = generate_answer(QUESTION, DOCUMENTS)
    except GroqAPIError as exc:
        raise SystemExit(f"Échec de l'appel Groq : {exc}") from None
    elapsed = time.perf_counter() - started

    print(f"Réponse : {answer}")
    print(f"Temps de génération : {elapsed:.2f} s")
    print(f"Modèle : {MODEL}")


if __name__ == "__main__":
    main()
