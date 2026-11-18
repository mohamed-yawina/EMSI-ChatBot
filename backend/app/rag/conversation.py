"""Stateless conversation helpers for follow-up retrieval."""
import re
import unicodedata

MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 4000
MAX_HISTORY_MESSAGE_CHARS = 1000
MIN_RETRIEVAL_SCORE = 0.20
RELATIVE_RETRIEVAL_SCORE = 0.65

FOLLOW_UP_MARKERS = re.compile(
    r"\b(et|alors|celui|celle|ceux|celles|ceci|cela|ça|y|là-bas|la-bas|"
    r"son|sa|ses|leur|leurs|aussi|également|encore|ce campus|cette formation|"
    r"ce programme|ce diplôme|ce dernier|la précédente|le précédent)\b",
    re.IGNORECASE,
)

CAMPUS_LOCATIONS = (
    ("Casa Anfa", re.compile(r"\bcasa\s+anfa\b", re.IGNORECASE)),
    ("Casablanca", re.compile(r"\bcasablanca\b", re.IGNORECASE)),
    ("Marrakech", re.compile(r"\bmarrakech\b", re.IGNORECASE)),
    ("Rabat", re.compile(r"\brabat\b", re.IGNORECASE)),
    ("Fès", re.compile(r"\bf[eè]s\b", re.IGNORECASE)),
    ("Tanger", re.compile(r"\btanger\b", re.IGNORECASE)),
)


def normalize_history(history) -> list[dict[str, str]]:
    """Return a bounded request-local history; never stores it globally."""
    if not isinstance(history, (list, tuple)):
        return []
    normalized = []
    remaining = MAX_HISTORY_CHARS
    for item in reversed(history[-MAX_HISTORY_MESSAGES:]):
        if isinstance(item, dict):
            role, content = item.get("role"), item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = re.sub(r"\s+", " ", content).strip()
        if not content or remaining <= 0:
            continue
        content = content[-min(MAX_HISTORY_MESSAGE_CHARS, remaining):]
        normalized.append({"role": role, "content": content})
        remaining -= len(content)
    return list(reversed(normalized))


def is_follow_up(question: str) -> bool:
    question = re.sub(r"\s+", " ", str(question or "")).strip()
    return bool(FOLLOW_UP_MARKERS.search(question))


def is_campus_enumeration_question(question: str) -> bool:
    """Recognize questions asking for named campus locations, not their count."""
    normalized = _normalized_search_text(question)
    if _locations(normalized):
        # A location-specific request may ask for branch names and addresses.
        return False
    asks_for_items = bool(re.search(
        r"\b(quels?|quelles?|lesquels?|lesquelles?|noms?|liste|citez|mentionnes?)\b",
        normalized,
    ))
    asks_about_campuses = bool(re.search(r"\bcampus\b", normalized))
    return asks_for_items and asks_about_campuses


def _locations(text: str) -> list[str]:
    return [name for name, pattern in CAMPUS_LOCATIONS if pattern.search(text)]


def _latest_unambiguous_location(turns) -> str | None:
    for turn in reversed(turns):
        locations = _locations(turn["content"])
        if len(locations) == 1:
            return locations[0]
        if len(locations) > 1:
            return None
    return None


def resolve_campus_reference(question: str, history) -> str | None:
    """Resolve an explicit or recent singular campus location for this turn."""
    current_locations = _locations(question)
    if len(current_locations) == 1:
        return current_locations[0]
    if len(current_locations) > 1:
        return None

    turns = normalize_history(history)
    if not turns or not is_follow_up(question):
        return None
    user_turns = [turn["content"] for turn in turns if turn["role"] == "user"]
    if not user_turns:
        return None
    # Preserve a campus referent across follow-ups even when an intermediate
    # assistant answer omits "campus". A standalone user question breaks the chain.
    has_campus_topic = False
    for prior_question in reversed(user_turns):
        if re.search(r"\b(campus|implantation|site)\b", prior_question, re.I):
            has_campus_topic = True
            break
        if not is_follow_up(prior_question):
            break
    if not has_campus_topic:
        return None
    return _latest_unambiguous_location(turns)


def requested_campus_offerings(question: str, history) -> str | None:
    """Return the campus when the user asks about local study offerings."""
    asks_about_programs = bool(re.search(
        r"\b(formation|formations|fili[eè]re|fili[eè]res|programme|programmes|sp[eé]cialit[eé])\b",
        question,
        re.IGNORECASE,
    ))
    if not asks_about_programs:
        return None
    return resolve_campus_reference(question, history)


def build_retrieval_query(question: str, history) -> str:
    """Create a standalone Qdrant query; history supplies referents, not appended evidence."""
    question = re.sub(r"\s+", " ", str(question or "")).strip()
    turns = normalize_history(history)
    if is_campus_enumeration_question(question):
        return (
            "Noms et villes des campus EMSI explicitement mentionnés dans la brochure : "
            + question
        )
    if not turns or not is_follow_up(question):
        return question

    location = resolve_campus_reference(question, turns)
    if location:
        if requested_campus_offerings(question, turns):
            return f"Formations proposées spécifiquement sur le campus EMSI de {location}"
        return f"Informations sur le campus EMSI de {location} dans la brochure"

    # For other follow-ups, retain only the immediately preceding user topic and
    # express the new information need in a compact standalone query.
    previous_question = next(
        (turn["content"] for turn in reversed(turns) if turn["role"] == "user"),
        "",
    )
    if not previous_question:
        return question
    topic = re.sub(r"\s+", " ", previous_question).strip().rstrip("?.! ")
    return f"{topic} — {question}".strip()


def _normalized_search_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(char for char in text if not unicodedata.combining(char))


def find_explicit_campus_names(text: str) -> list[str]:
    """Return only known campus names that occur literally in a document passage."""
    normalized = _normalized_search_text(text)
    matches = []
    for canonical_name, pattern in CAMPUS_LOCATIONS:
        match = pattern.search(normalized)
        if match:
            matches.append((match.start(), canonical_name))
    return [name for _, name in sorted(matches)]


def campus_offering_evidence_documents(documents, location: str) -> list[dict]:
    """Return only sentences that explicitly link a campus and an offering."""
    normalized_location = _normalized_search_text(location)
    city = re.escape(normalized_location).replace(r"\ ", r"\s+")
    campus = rf"(?:campus|site|etablissement)(?:\s+emsi)?\s+(?:de|d')\s+{city}"
    local_campus = rf"(?:(?:au|sur le|dans le)\s+)?{campus}"
    program = r"(?:formations?|filieres?|programmes?|specialites?|diplomes?)"
    active_offer = r"(?:propos\w*|offr\w*|dispens\w*|enseign\w*|disponib\w*)"
    passive_offer = r"(?:propos\w*|offr\w*|dispens\w*|enseign\w*)"
    patterns = (
        re.compile(rf"\b{local_campus}\s+(?:propose|offre|dispense|enseigne)\b.{{0,45}}\b{program}\b"),
        re.compile(rf"\b{program}\b.{{0,65}}\b{passive_offer}\b.{{0,25}}\b(?:au|sur le|dans le)\s+{campus}\b"),
        re.compile(rf"\b(?:au|sur le|dans le)\s+{campus}\s*[, :]\s*.{{0,35}}\b{program}\b.{{0,100}}\b{active_offer}\b"),
        re.compile(rf"\b(?:a|sur le site de)\s+{city}\s*[, :]\s*.{{0,35}}\b{program}\b.{{0,100}}\b{active_offer}\b"),
        re.compile(rf"\b{program}\b.{{0,65}}\b{passive_offer}\b.{{0,25}}\b(?:a|au)\s+{city}\b"),
    )
    supported = []
    for document in documents:
        original_text = str(document.get("content", ""))
        sentences = re.split(r"(?<=[.!?])\s+|[;\n]+", original_text)
        matched = [
            sentence.strip()
            for sentence in sentences
            if sentence.strip()
            and any(pattern.search(_normalized_search_text(sentence)) for pattern in patterns)
        ]
        if matched:
            supported.append({**document, "content": " ".join(matched)})
    return supported


def has_campus_offering_evidence(documents, location: str) -> bool:
    """Require an explicit local offering relationship within one sentence."""
    return bool(campus_offering_evidence_documents(documents, location))


def has_general_offering_information(documents) -> bool:
    """Detect general course information for a useful, scoped limitation message."""
    program = re.compile(r"\b(formations?|filieres?|programmes?|specialites?|diplomes?)\b", re.I)
    offer = re.compile(r"\b(propos\w*|offr\w*|dispens\w*|enseign\w*|disponib\w*)\b", re.I)
    return any(
        program.search(str(document.get("content", "")))
        and offer.search(str(document.get("content", "")))
        for document in documents
    )


def select_relevant_documents(documents, limit: int = 4) -> list[dict]:
    """Discard weak ranking tails while preserving the retriever's original scores."""
    scored = []
    for document in documents:
        try:
            score = float(document.get("score"))
        except (TypeError, ValueError):
            continue
        scored.append((score, document))
    if not scored:
        return []

    best_score = max(score for score, _ in scored)
    threshold = max(MIN_RETRIEVAL_SCORE, best_score * RELATIVE_RETRIEVAL_SCORE)
    return [document for score, document in scored if score >= threshold][:max(1, limit)]
