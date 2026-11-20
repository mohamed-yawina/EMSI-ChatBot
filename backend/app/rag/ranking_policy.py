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


def is_exhaustive_program_question(question: str) -> bool:
    """Recognize requests for a full list of study programs, not specific facts."""
    query = unicodedata.normalize("NFKD", repair_common_mojibake(str(question).lower()))
    query = "".join(char for char in query if not unicodedata.combining(char))
    explicit_list = bool(re.search(
        r"\b(tous|toutes|liste|lister|ensemble|complet(?:e|es|s)?)\b", query
    ))
    specific_detail = bool(re.search(
        r"\b(duree|durees|debouche|debouches|condition|conditions|admission|"
        r"debute|debutee|cout|frais|acces|admissibilite)\b", query
    ))
    if specific_detail and not explicit_list:
        return False
    plural_program = bool(re.search(
        r"\b(filieres|formations|programmes|specialites)\b", query
    ))
    curriculum_query = bool(re.search(
        r"\b(quels|quelles|lesquels|lesquelles)\b.{0,45}"
        r"\b(filieres|formations|programmes|specialites)\b",
        query,
    ))
    proposed_programs = plural_program and bool(re.search(
        r"\b(propos\w*|offr\w*|disponibl\w*|existant\w*)\b", query
    ))
    curriculum_list = bool(re.search(
        r"\b(quels|quelles|lesquels|lesquelles)\b.{0,35}\bcursus\b|"
        r"\b(?:tous|toutes|liste|lister|ensemble)\b.{0,35}\bcursus\b",
        query,
    ))
    asks_for_program_collection = (
        explicit_list and bool(re.search(
            r"\b(filieres?|formations?|programmes?|specialites?|cursus)\b", query
        ))
    ) or curriculum_query or proposed_programs or curriculum_list
    return asks_for_program_collection


def is_program_duration_question(question: str) -> bool:
    """Detect a duration question about a particular curriculum, not general lists."""
    query = unicodedata.normalize("NFKD", repair_common_mojibake(str(question).lower()))
    query = "".join(char for char in query if not unicodedata.combining(char))
    asks_duration = bool(re.search(
        r"\b(duree|durees|combien d'annees|combien d'annee|longtemps)\b", query
    ))
    if not asks_duration:
        return False
    program_terms = set(re.findall(r"[a-z0-9]+", query)) - {
        "quelle", "quelles", "quel", "quels", "est", "sont", "la", "le",
        "les", "de", "du", "des", "d", "en", "pour", "une", "un",
        "formation", "formations", "filiere", "filieres", "cursus",
        "programme", "programmes", "proposee", "proposees", "emsi",
        "duree", "durees", "combien", "annee", "annees", "longtemps",
    }
    return bool(program_terms)


def program_duration_catalog_bonus(question: str, content: str) -> float:
    """Promote existing curriculum summaries only for a matching duration query."""
    if not is_program_duration_question(question):
        return 0.0
    normalized_content = unicodedata.normalize(
        "NFKD", repair_common_mojibake(str(content).lower())
    )
    normalized_content = "".join(
        char for char in normalized_content if not unicodedata.combining(char)
    )
    cycle_count = len(re.findall(
        r"\b\d+\s+annees?\s+cycle\s+d['’]?\s*ingenieur\b",
        normalized_content,
    ))
    has_preparatory_or_options = bool(re.search(
        r"\bannees?\s+preparatoires?\b|\boptions?\s+\d+\b",
        normalized_content,
    ))
    if cycle_count < 1 or not has_preparatory_or_options:
        return 0.0
    normalized_query = unicodedata.normalize(
        "NFKD", repair_common_mojibake(str(question).lower())
    )
    normalized_query = "".join(
        char for char in normalized_query if not unicodedata.combining(char)
    )
    query_terms = set(re.findall(r"[a-z0-9]+", normalized_query))
    query_terms = {
        term for term in query_terms
        if term not in {
            "quelle", "quelles", "quel", "quels", "est", "sont", "la", "le",
            "les", "de", "du", "des", "d", "en", "pour", "une", "un",
            "formation", "formations", "filiere", "filieres", "cursus", "programme",
            "programmes", "proposee", "proposees", "emsi", "duree", "durees",
            "combien", "annee", "annees", "longtemps",
        }
    }
    content_terms = set(re.findall(r"[a-z0-9]+", normalized_content))
    if not query_terms or not query_terms.issubset(content_terms):
        return 0.0
    return 0.18


def program_catalog_bonus(
    question: str,
    content: str,
    *,
    exhaustive: bool | None = None,
) -> float:
    """Promote structurally catalog-like passages for exhaustive program queries.

    This uses repeated curriculum structure rather than a hard-coded program list.
    """
    if exhaustive is None:
        exhaustive = is_exhaustive_program_question(question)
    if not exhaustive or is_historical_program_timeline(content):
        return 0.0
    text = unicodedata.normalize("NFKD", repair_common_mojibake(str(content).lower()))
    text = "".join(char for char in text if not unicodedata.combining(char))
    curriculum_markers = sum((
        len(re.findall(r"\bcycle\s+d['’]?ingenieur\b", text)) >= 2,
        len(re.findall(r"\bannees? preparatoires?\b", text)) >= 2,
        len(re.findall(r"\b(?:genie|ingenierie)\b", text)) >= 3,
    ))
    return 0.18 if curriculum_markers >= 2 else 0.0


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
