import re
import unicodedata

from app.rag.conversation import (
    find_explicit_campus_names,
    is_campus_enumeration_question,
)


def is_historical_program_timeline(content: str) -> bool:
    """Repère une annonce datée qui associe explicitement un événement à un cursus."""
    text = unicodedata.normalize("NFKD", str(content).lower())
    text = "".join(char for char in text if not unicodedata.combining(char))

    has_year = re.search(r"\b(?:19|20)\d{2}\b", text) is not None
    has_program_event = re.search(
        r"\b(?:demarrage|creation|ouverture|lancement)\b.{0,60}"
        r"\b(?:filiere|formation|specialite)\b",
        text,
    ) is not None
    return has_year and has_program_event


def should_apply_program_topic_bonus(question: str, content: str) -> bool:
    """Garde le bonus des requêtes programmes sauf pour les annonces historiques."""
    query = unicodedata.normalize("NFKD", str(question).lower())
    query = "".join(char for char in query if not unicodedata.combining(char))
    asks_for_programs = any(
        term in query for term in ("filiere", "formation", "specialite")
    )
    return asks_for_programs and not is_historical_program_timeline(content)


def campus_list_bonus(question: str, content: str) -> float:
    """Promote a passage that names multiple campuses for a list query."""
    if not is_campus_enumeration_question(question):
        return 0.0
    normalized_content = unicodedata.normalize("NFKD", str(content).lower())
    normalized_content = "".join(
        char for char in normalized_content if not unicodedata.combining(char)
    )
    if not re.search(r"\bcampus\b", normalized_content):
        return 0.0
    return 0.18 if len(find_explicit_campus_names(content)) >= 2 else 0.0
