"""Groq Chat Completions adapter; sends only retrieved brochure passages."""
import logging
import os
import re
import time
import unicodedata

import httpx

logger = logging.getLogger("emsi-chatbot.groq")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = os.getenv("GROQ_MODEL", "").strip()
MAX_DOCUMENTS = 4
MAX_CHARS_PER_DOCUMENT = 700
REFERENCE_TOKEN = re.compile(r"\[\[REF:([A-Z])\]\]")
UNVERIFIED_REFERENCE = "[référence non vérifiée]"


class GroqAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]
    return truncated.rstrip() + "..."


def build_context_with_references(documents: list) -> tuple[str, dict[str, dict]]:
    passages = []
    references = {}
    for doc in documents[:MAX_DOCUMENTS]:
        content = clean_text(doc.get("content", ""))
        if not content:
            continue
        source = clean_text(doc.get("source", ""))
        page = doc.get("page")
        if not source or page in (None, "", "?"):
            source, page = "", None
        reference_id = chr(ord("A") + len(references))
        references[reference_id] = {"source": source, "page": page, "document": doc}
        passages.append(
            f"[PASSAGE {reference_id}]\n"
            f"Source PDF : {source or 'métadonnée absente'}\n"
            f"Page PDF réelle : {page if page is not None else 'métadonnée absente'}\n"
            f"Texte : {truncate_text(content, MAX_CHARS_PER_DOCUMENT)}"
        )
    return "\n\n".join(passages), references


def build_context(documents: list) -> str:
    return build_context_with_references(documents)[0]


def resolve_answer_references(answer: str, references: dict[str, dict]) -> str:
    answer = clean_text(answer)
    answer = re.sub(r"\((?:page|p\.)\s*\d+\)|\bpage\s+\d+\b|\bp\.\s*\d+\b", UNVERIFIED_REFERENCE, answer, flags=re.IGNORECASE)

    def replace(match):
        entry = references.get(match.group(1))
        if not entry or not entry.get("source") or entry.get("page") is None:
            return UNVERIFIED_REFERENCE
        return f"({entry['source']}, page {entry['page']})"

    answer = REFERENCE_TOKEN.sub(replace, answer)
    return re.sub(r"\[\[REF:[^\]]*\]\]", UNVERIFIED_REFERENCE, answer)


def get_cited_documents(answer: str, references: dict[str, dict]) -> list[dict]:
    cited = []
    seen = set()
    for entry in references.values():
        document = entry.get("document")
        if not document or not entry.get("source") or entry.get("page") is None:
            continue
        citation = f"({entry['source']}, page {entry['page']})"
        key = (entry["source"], str(entry["page"]))
        if citation in answer and key not in seen:
            cited.append(document)
            seen.add(key)
    return cited


def _has_ambiguous_timeline(documents: list) -> bool:
    terms = re.compile(r"\b(ouverture|création|demarrage|démarrage|adhésion|lancement)\b", re.I)
    return any(
        len(set(re.findall(r"\b(?:19|20)\d{2}\b", clean_text(doc.get("content", ""))))) >= 3
        and terms.search(clean_text(doc.get("content", "")))
        for doc in documents[:MAX_DOCUMENTS]
    )


def _has_ambiguous_year_event_claim(answer: str) -> bool:
    """Only flag a date when the answer links a year to a campus/location event."""
    text = unicodedata.normalize("NFKD", clean_text(answer).lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    place = r"(?:casa\s+anfa|casablanca|marrakech|rabat|fes|tanger|campus\s+emsi)"
    year = r"(?:19|20)\d{2}"
    event = r"(?:ouverture|a\s+ouvert|cree|creation|demarrage|lancement|adhesion|inaugur\w*|opened|founded)"
    patterns = (
        rf"\b{place}\b.{{0,50}}\b{event}\b.{{0,35}}\b{year}\b",
        rf"\b{year}\b.{{0,35}}\b{event}\b.{{0,50}}\b{place}\b",
        rf"\b{event}\b.{{0,40}}\b{place}\b.{{0,35}}\b{year}\b",
        rf"\b{place}\b\s*(?:\(|en|depuis)\s*\b{year}\b",
    )
    sentences = re.split(r"[.!?;]+", text)
    return any(re.search(pattern, sentence) for sentence in sentences for pattern in patterns)


def build_prompt(question: str, context: str, history=None) -> str:
    from app.rag.conversation import normalize_history
    turns = normalize_history(history)
    history_context = "\n".join(
        f"{turn['role'].upper()}: {turn['content']}"
        for turn in turns
    )
    history_section = (
        "\nHISTORIQUE CONVERSATIONNEL — CONTEXTE DE RÉFÉRENCE SEULEMENT, PAS UNE SOURCE DOCUMENTAIRE. "
        "N'utilise aucun fait provenant de l'historique comme preuve.\n"
        f"{history_context}\n"
        if history_context else ""
    )
    # Consignes documentaires conservées de l'ancien service.
    return f"""Tu es EMSI-ChatBot, un assistant documentaire.

Ta mission est de répondre à la question de l'utilisateur
en utilisant EXCLUSIVEMENT les passages documentaires.

RÈGLES STRICTES :

1. Utilise uniquement les informations explicitement présentes dans les documents.
2. N'invente aucun nom de laboratoire, aucun équipement, aucun chiffre et aucune caractéristique.
3. Ne transforme jamais une formation, un diplôme, un enseignant, un club, une activité ou un partenariat en équipement.
4. Si la question porte sur les équipements, cite uniquement les équipements ou installations réellement mentionnés dans le contexte.
5. Si la question porte sur les laboratoires, cite uniquement les laboratoires réellement mentionnés.
6. Si le contexte indique un nombre de laboratoires, tu peux le mentionner et associer le jeton de passage concerné.
7. Si le contexte ne fournit pas de liste détaillée, indique clairement que cette liste n'est pas précisée.
8. N'utilise pas tes connaissances générales pour compléter les informations manquantes.
9. Chaque affirmation doit être justifiable par au moins un passage fourni.
10. Chaque passage porte un identifiant alphabétique PASSAGE A, B, etc. Cet identifiant n'est PAS un numéro de page PDF. Pour citer une information, insère uniquement le jeton [[REF:A]] correspondant au passage utilisé. N'écris jamais toi-même un numéro ou nom de page; le serveur ajoute la citation exacte depuis Qdrant.
11. Réponds en français simple, avec des phrases courtes, précises et grammaticalement complètes.
12. Ne répète pas les mêmes informations.
13. Si les passages fournis ne répondent pas explicitement à la question actuelle, réponds exactement :
"Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
14. Respecte exactement les noms, dates, chiffres et événements présents. N'infère pas qu'une année proche dans le texte appartient à une ville ou un événement : si la mise en page rend le lien ambigu, dis que la date n'est pas vérifiable.
15. Pour une question demandant une liste, relève chaque élément distinct explicitement
    nommé dans tous les passages et inclus-le dans la réponse avec le jeton de passage correspondant. Vérifie la liste
    une seconde fois avant de répondre, sans déduire d'éléments absents des documents.
16. Utilise l'historique uniquement pour résoudre les pronoms et le sujet implicite de la question actuelle; il ne prouve aucun fait. Si l'utilisateur demande quelles formations sont proposées sur un campus précis, ne déduis jamais l'offre locale d'une liste générale de formations EMSI. Si les passages ne confirment pas cette association, indique que la brochure ne la précise pas.

17. Si une question de suivi vise un campus sans demander son histoire ni une date, rÃ©ponds aux informations documentÃ©es sur ce campus et n'ajoute pas spontanÃ©ment une annÃ©e ou un Ã©vÃ©nement historique.

18. Si l'utilisateur demande quels sont les campus ou leurs noms, énumère chaque nom explicitement présent dans les passages. Un nombre total de campus ne remplace jamais la liste. Présente la liste comme celle des noms retrouvés dans les passages, sans prétendre qu'elle est exhaustive si les documents ne l'affirment pas.

EXEMPLE DE DISTINCTION :
- "150 laboratoires modernes" : information sur les laboratoires.
- "Plateformes de simulation" : installation.
- "800 enseignants" : personnel, PAS équipement.
- "Diplôme d'ingénieur" : formation, PAS équipement.

DOCUMENTS :
{context}

{history_section}

QUESTION :
{question}

RÉPONSE FACTUELLE EN FRANÇAIS :"""


def _campus_enumeration_answer(question: str, documents: list) -> str | None:
    """Build a cited campus list only from names and totals present in passages."""
    from app.rag.conversation import (
        find_explicit_campus_names,
        is_campus_enumeration_question,
    )

    if not is_campus_enumeration_question(question):
        return None

    ordered_documents = []
    for index, document in enumerate(documents[:MAX_DOCUMENTS]):
        try:
            page_order = int(document.get("page"))
        except (TypeError, ValueError):
            page_order = 10**9
        ordered_documents.append((page_order, index, document))
    ordered_documents.sort(key=lambda item: (item[0], item[1]))

    names_by_page: dict[tuple[str, str], list[str]] = {}
    totals_by_page: dict[tuple[str, str], list[int]] = {}
    seen_names = set()
    for _, _, document in ordered_documents:
        source = clean_text(document.get("source", ""))
        page = document.get("page")
        if not source or page in (None, "", "?") or isinstance(page, bool):
            continue
        try:
            if int(page) < 1:
                continue
        except (TypeError, ValueError):
            continue

        content = truncate_text(
            clean_text(document.get("content", "")),
            MAX_CHARS_PER_DOCUMENT,
        )
        normalized_content = unicodedata.normalize("NFKD", content.lower())
        normalized_content = "".join(
            char for char in normalized_content if not unicodedata.combining(char)
        )
        has_campus_context = bool(re.search(r"\bcampus\b", normalized_content))

        key = (source, str(page))
        page_names = names_by_page.setdefault(key, [])
        for name in find_explicit_campus_names(content):
            if not has_campus_context:
                normalized_name = unicodedata.normalize("NFKD", name.lower())
                normalized_name = "".join(
                    char for char in normalized_name
                    if not unicodedata.combining(char)
                )
                name_pattern = re.escape(normalized_name).replace(r"\ ", r"\s+")
                emsi_relation = re.search(
                    rf"\bemsi\b.{{0,30}}\b{name_pattern}\b|"
                    rf"\b{name_pattern}\b.{{0,30}}\bemsi\b",
                    normalized_content,
                )
                if not emsi_relation:
                    continue
            if name not in seen_names:
                page_names.append(name)
                seen_names.add(name)

        page_totals = totals_by_page.setdefault(key, [])
        if not has_campus_context:
            continue
        for raw_count in re.findall(r"\b(\d{1,3})\s+campus\b", normalized_content):
            count = int(raw_count)
            if count not in page_totals:
                page_totals.append(count)

    def citation(key: tuple[str, str]) -> str:
        return f"({key[0]}, page {key[1]})"

    name_parts = [
        f"{', '.join(names)} {citation(key)}"
        for key, names in names_by_page.items()
        if names
    ]
    total_parts = [
        (count, key)
        for key, counts in totals_by_page.items()
        for count in counts
    ]

    if name_parts:
        answer = (
            "Les noms de campus explicitement retrouvés dans les passages consultés sont : "
            + "; ".join(name_parts)
            + "."
        )
        if total_parts:
            count, key = total_parts[0]
            answer += (
                f" La brochure annonce séparément {count} campus au total ; "
                f"les passages consultés ne confirment pas que les noms retrouvés constituent "
                f"la liste complète. {citation(key)}"
            )
        return answer

    if total_parts:
        count, key = total_parts[0]
        return (
            f"La brochure annonce {count} campus au total, mais les passages consultés "
            f"ne donnent pas leurs noms. {citation(key)}"
        )
    return "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."


def generate_answer(question: str, documents: list, history=None) -> str:
    question = clean_text(question)
    if not question:
        return "Veuillez poser une question."
    if not documents:
        return "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    context, references = build_context_with_references(documents)
    if not context:
        return "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqAPIError("GROQ_API_KEY n'est pas configurée.", 503)
    model = os.getenv("GROQ_MODEL", MODEL).strip()
    if not model:
        raise GroqAPIError("GROQ_MODEL doit préciser un modèle Groq disponible.", 503)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": build_prompt(question, context, history)},
            {"role": "user", "content": question},
        ],
        "temperature": 0.5,
        "max_completion_tokens": 1024,
    }
    if model in {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}:
        payload["reasoning_effort"] = "low"
    started = time.perf_counter()
    try:
        response = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=httpx.Timeout(60.0, connect=5.0),
        )
        if response.status_code in (401, 403):
            logger.warning("Groq returned HTTP %s (authentication)", response.status_code)
            raise GroqAPIError("Authentification Groq refusée. Vérifiez GROQ_API_KEY.", 503)
        if response.status_code == 429:
            logger.warning("Groq returned HTTP 429 (quota/rate limit)")
            raise GroqAPIError("Quota ou limite de débit Groq atteint. Réessayez plus tard.", 503)
        if response.status_code >= 400:
            logger.warning("Groq returned HTTP %s", response.status_code)
            raise GroqAPIError(f"Erreur HTTP Groq ({response.status_code}). Vérifiez le modèle et la requête.", 502)
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice.get("message") or {}
            finish_reason = choice.get("finish_reason")
            answer = clean_text(message.get("content"))
            usage = data.get("usage") or {}
            completion_details = usage.get("completion_tokens_details") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            reasoning_tokens = completion_details.get("reasoning_tokens")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise GroqAPIError("Réponse JSON Groq invalide ou vide.", 502) from exc
        elapsed = time.perf_counter() - started
        diagnostic = (
            "Groq terminé en %.2fs | finish_reason=%s | prompt_tokens=%s | "
            "completion_tokens=%s | reasoning_tokens=%s | answer_chars=%s"
        )
        diagnostic_values = (
            elapsed,
            finish_reason,
            prompt_tokens,
            completion_tokens,
            reasoning_tokens,
            len(answer),
        )
        if finish_reason == "length":
            logger.warning("Limite de tokens Groq atteinte | " + diagnostic, *diagnostic_values)
            raise GroqAPIError(
                "Groq a atteint max_completion_tokens avant de terminer la réponse.",
                502,
            )
        if not answer:
            logger.warning("Contenu Groq vide | " + diagnostic, *diagnostic_values)
            raise GroqAPIError("Groq a renvoyé un contenu vide sans atteindre la limite de tokens.", 502)
        logger.info(diagnostic, *diagnostic_values)
        answer = resolve_answer_references(answer, references)
        campus_answer = _campus_enumeration_answer(question, documents)
        if campus_answer is not None:
            answer = campus_answer
        has_verified_citation = bool(get_cited_documents(answer, references))
        safe_no_info = answer == "Je n'ai pas trouvé cette information dans les documents EMSI disponibles."
        if not has_verified_citation and not safe_no_info:
            answer = "Les documents consultés ne permettent pas de vérifier cette réponse (référence non vérifiée)."
        mentioned_years = set(re.findall(r"\b(?:19|20)\d{2}\b", answer))
        source_years = set(re.findall(
            r"\b(?:19|20)\d{2}\b",
            " ".join(clean_text(doc.get("content", "")) for doc in documents[:MAX_DOCUMENTS]),
        ))
        cited_documents = get_cited_documents(answer, references)
        citations = " ".join(
            f"({doc['source']}, page {doc['page']})"
            for doc in cited_documents
        )
        if mentioned_years - source_years:
            answer = "La date indiquée dans la réponse n'est pas vérifiable dans les passages consultés. " + citations
        elif (
            mentioned_years
            and _has_ambiguous_timeline(documents)
            and _has_ambiguous_year_event_claim(answer)
        ):
            answer = (
                "La brochure contient plusieurs dates et événements dans un extrait dont la mise en page est ambiguë. "
                "L'association entre l'année et l'événement demandé n'est pas vérifiable dans ces passages. "
                + citations
            ).strip()
        return answer
    except httpx.TimeoutException as exc:
        raise GroqAPIError("Délai d'attente dépassé lors de l'appel à Groq.", 504) from exc
    except httpx.ConnectError as exc:
        raise GroqAPIError("Connexion HTTPS à Groq impossible.", 502) from exc
    except httpx.HTTPError as exc:
        raise GroqAPIError("Erreur de communication avec Groq.", 502) from exc
