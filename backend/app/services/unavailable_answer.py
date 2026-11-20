"""Question-aware wording for information absent from the EMSI documents."""

import re
import unicodedata


GENERIC_UNAVAILABLE_ANSWER = (
    "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
)


def _normalize_question(question: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(question or "").lower())
    without_marks = "".join(
        character for character in normalized
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_marks.replace("’", "'")).strip()


def unavailable_answer(question: str) -> str:
    """Return a cautious, useful fallback without adding undocumented facts."""
    normalized = _normalize_question(question)

    asks_admission = bool(re.search(
        r"\b(admission|admissions|admissibilite|prerequis|baccalaureat|"
        r"diplome requis|modalites de selection|conditions? d'acces)\b",
        normalized,
    ))
    if asks_admission:
        return (
            "Je n'ai pas trouvé les conditions d'admission dans les documents EMSI "
            "actuellement disponibles. Pour connaître les diplômes requis, les "
            "modalités de sélection et les documents à fournir, je vous conseille "
            "de contacter le service des admissions de l'EMSI. Je peux également "
            "vous renseigner sur les filières et les formations présentées dans "
            "la brochure."
        )

    asks_fees = bool(re.search(
        r"\b(frais|cout|couts|tarif|tarifs|scolarite|prix)\b", normalized
    ))
    if asks_fees:
        return (
            "Je n'ai pas trouvé les frais de scolarité dans les documents EMSI "
            "disponibles. Pour obtenir un montant fiable, contactez l'EMSI ; je "
            "peux aussi vous renseigner sur les formations décrites dans la brochure."
        )

    asks_application_details = bool(re.search(
        r"\b(candidature|candidatures|candidater|inscri\w*|dossier|"
        r"date limite|dates limites)\b", normalized
    ))
    if asks_application_details:
        return (
            "Je n'ai pas trouvé les modalités ou les échéances de candidature "
            "dans les documents EMSI disponibles. Contactez l'EMSI pour obtenir "
            "ces détails."
        )

    return GENERIC_UNAVAILABLE_ANSWER


def is_admission_question(question: str) -> bool:
    normalized = _normalize_question(question)
    return bool(re.search(
        r"\b(admission|admissions|admissibilite|prerequis|baccalaureat|"
        r"diplome requis|modalites de selection|conditions? d'acces)\b",
        normalized,
    ))


def has_explicit_admission_criteria(documents: list[dict]) -> bool:
    """Require actual eligibility language; a testimonial or apply CTA is insufficient."""
    criteria_patterns = (
        r"\bconditions? d'admission\b.{0,160}"
        r"\b(diplome|bac|baccalaureat|niveau|concours|selection|note|dossier)\b",
        r"\bconditions? d'acces\b.{0,160}"
        r"\b(diplome|bac|baccalaureat|niveau|concours|selection|note|dossier)\b",
        r"\bprerequis\b.{0,100}"
        r"\b(diplome|bac|baccalaureat|niveau|concours|selection|note|dossier)\b",
        r"\bdiplome requis\b",
        r"\bniveau requis\b",
        r"\btitulaires?\b.{0,80}"
        r"\b(diplome|bac|baccalaureat|niveau)\b",
        r"\b(candidat(?:e)?s?|admission|admis)\b.{0,100}"
        r"\b(diplome|bac|baccalaureat|niveau|concours|selection|note|dossier)\b",
        r"\b(diplome|bac|baccalaureat|niveau requis|selection)\b.{0,100}"
        r"\b(admission|admis|candidat(?:e)?s?)\b",
        r"\badmission\b.{0,100}\b(soumise|subordonnee|conditionnee)\b.{0,60}\bconcours\b",
        r"\bconcours\b.{0,100}\b(condition|admission|requis|obligatoire)\b",
    )
    for document in documents:
        content = _normalize_question(document.get("content", ""))
        if any(re.search(pattern, content) for pattern in criteria_patterns):
            return True
    return False


def is_unavailable_answer(answer: str) -> bool:
    """Recognize only the explicit no-information fallbacks used by this app."""
    value = _normalize_question(answer)
    return value.startswith("je n'ai pas trouve ")
