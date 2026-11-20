import re
import unicodedata

from app.rag.conversation import (
    find_explicit_campus_names,
    is_campus_enumeration_question,
)


_MOJIBAKE_MARKERS = re.compile(r"(?:\u00c3|\u00e2|\u00c2|\u00ef\u00ac)")
_NON_ASCII_RUN = re.compile(r"[^\x00-\x7f]+")


def repair_common_mojibake(value: str) -> str:
    """Repair common UTF-8-as-Windows-1252 text corruption without guessing.

    Only byte runs that decode strictly as UTF-8 and reduce known mojibake
    markers are changed. Other Unicode text is retained byte-for-byte.
    """
    text = str(value or "")
    for _ in range(2):
        if not _MOJIBAKE_MARKERS.search(text):
            break

        def repair_run(match: re.Match[str]) -> str:
            run = match.group(0)
            before = len(_MOJIBAKE_MARKERS.findall(run))
            for encoding in ("cp1252", "latin-1"):
                try:
                    repaired = run.encode(encoding).decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
                if repaired != run and len(_MOJIBAKE_MARKERS.findall(repaired)) < before:
                    return repaired
            return run

        repaired_text = _NON_ASCII_RUN.sub(repair_run, text)
        if repaired_text == text:
            break
        text = repaired_text
    return text


def is_historical_program_timeline(content: str) -> bool:
    """RepÃ¨re une annonce datÃ©e qui associe explicitement un Ã©vÃ©nement Ã  un cursus."""
    text = unicodedata.normalize(
        "NFKD", repair_common_mojibake(str(content).lower())
    )
    text = "".join(char for char in text if not unicodedata.combining(char))

    has_year = re.search(r"\b(?:19|20)\d{2}\b", text) is not None
    has_program_event = re.search(
        r"\b(?:demarrage|creation|ouverture|lancement)\b.{0,60}"
        r"\b(?:filiere|formation|specialite)\b",
        text,
    ) is not None
    return has_year and has_program_event


def should_apply_program_topic_bonus(question: str, content: str) -> bool:
    """Garde le bonus des requÃªtes programmes sauf pour les annonces historiques."""
    query = unicodedata.normalize("NFKD", repair_common_mojibake(str(question).lower()))
    query = "".join(char for char in query if not unicodedata.combining(char))
    asks_for_programs = any(
        term in query for term in ("filiere", "formation", "specialite")
    )
    return asks_for_programs and not is_historical_program_timeline(content)


def campus_list_bonus(question: str, content: str) -> float:
    """Promote a passage that names multiple campuses for a list query."""
    if not is_campus_enumeration_question(question):
        return 0.0
    normalized_content = unicodedata.normalize(
        "NFKD", repair_common_mojibake(str(content).lower())
    )
    normalized_content = "".join(
        char for char in normalized_content if not unicodedata.combining(char)
    )
    if not re.search(r"\bcampus\b", normalized_content):
        return 0.0
    return 0.18 if len(find_explicit_campus_names(content)) >= 2 else 0.0
