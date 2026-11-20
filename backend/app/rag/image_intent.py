"""Conservative image-request and person-reference detection."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").lower())
    return "".join(c for c in value if not unicodedata.combining(c))


@dataclass(frozen=True)
class ImageIntent:
    requested: bool
    query: str
    person_target: str | None = None
    mode: str = "generic"


_IMAGE_WORDS = re.compile(r"\b(photo(?:s)?|image(?:s)?|portrait|visuel(?:s)?|illustration(?:s)?)\b")
_PERSON_ROLES = re.compile(
    r"\b((?:directeur|directrice) general(?:e)?|president(?:e)?|fondateur|fondatrice|"
    r"doyen(?:ne)?|professeur(?:e)?|responsable)\b"
)
_PERSON_REQUEST = re.compile(r"\b(photo|image|portrait)\s+(?:de la|de|du|d\s*\x27)\s+(.+)$")
_ANAPHOR = re.compile(r"\b(sa|son|ses)\s+(?:photo|image|portrait)\b")
_EVENT_WORDS = re.compile(r"\b(evenement|conference|ceremonie|remise des diplomes|forum|journee portes ouvertes)\b")
_EVENT_SUBJECT = re.compile(
    r"^(?:l\s+)?(?:evenement|conference|ceremonie|remise des diplomes|forum|"
    r"journee portes ouvertes)\b"
)


def resolve_image_intent(question: str, history=()) -> ImageIntent:
    """Classify explicit image requests; resolve simple possessive follow-ups."""
    normalized = _norm(question).strip()
    requested = bool(_IMAGE_WORDS.search(normalized)) or bool(
        re.search(
            r"\b(montre|affiche)\b.+\b(campus|batiment|ecole|laboratoire|labo|"
            r"evenement|conference|ceremonie|forum)\b",
            normalized,
        )
    )
    if not requested:
        return ImageIntent(False, question.strip())

    target = normalized
    if _ANAPHOR.search(normalized):
        previous_user = next(
            (str(turn.get("content", "")) for turn in reversed(history)
             if isinstance(turn, dict) and turn.get("role") == "user"),
            "",
        )
        previous = _norm(previous_user)
        role = _PERSON_ROLES.search(previous)
        if role:
            target = f"photo du {role.group(1)}"
        else:
            # A campus referent is safe as an image search phrase, but does not
            # imply that a picture depicts an individual.
            campus = re.search(r"\b(casablanca|rabat|marrakech|fes|tanger|casa anfa)\b", previous)
            if campus:
                target = f"photo du campus {campus.group(1)}"

    person_match = _PERSON_REQUEST.search(target)
    person_target = person_match.group(2).strip(" .?!") if person_match else None
    if person_target:
        if _EVENT_SUBJECT.match(person_target):
            # A grammatical object beginning with an event is not evidence
            # that the request targets a person ("photo de la cérémonie...").
            person_target = None
        elif re.match(r"^(?:campus|site|batiment|ecole|logo|ville|brochure)\b", person_target):
            person_target = None
        else:
            role = _PERSON_ROLES.search(person_target)
            if role:
                person_target = role.group(0)
    if person_target:
        mode = "person"
    elif _EVENT_WORDS.search(target):
        mode = "event"
    elif re.search(r"\b(campus|site|implantation)\b", target):
        mode = "campus"
    elif re.search(r"\b(laboratoire|labo|atelier|salle)\b", target):
        mode = "laboratory"
    elif re.search(r"\b(brochure|document|documents)\b", target):
        mode = "brochure"
    else:
        mode = "generic"
    return ImageIntent(True, target, person_target, mode)


def image_matches_person_evidence(image: dict, documents: list[dict], target: str) -> bool:
    """Require same-page text evidence and an explicit identifying caption."""
    if image.get("caption_verified") is not True:
        return False
    caption = _norm(image.get("caption") or "")
    wanted = _norm(target).strip()
    if not caption or not wanted or wanted not in caption:
        return False
    source = str(image.get("source", "")).casefold()
    page = str(image.get("page", ""))
    return any(
        str(doc.get("source", "")).casefold() == source
        and str(doc.get("page", "")) == page
        and wanted in _norm(doc.get("content", ""))
        for doc in documents
    )
