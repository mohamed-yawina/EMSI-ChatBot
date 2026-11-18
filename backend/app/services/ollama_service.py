
import logging
import os
import re
import time

import requests


# =====================================================
# CONFIGURATION
# =====================================================

logger = logging.getLogger("emsi-chatbot.ollama")

OLLAMA_URL = os.getenv(
    "EMSI_OLLAMA_URL",
    "http://127.0.0.1:11434/api/generate"
)

MODEL = os.getenv(
    "EMSI_OLLAMA_MODEL",
    "qwen2.5:1.5b"
)

MAX_DOCUMENTS = 3
MAX_CHARS_PER_DOCUMENT = 700

NUM_CTX = 2048
NUM_PREDICT = 160
NUM_THREADS = 2

KEEP_ALIVE = "0s"


# =====================================================
# PRÉPARATION DU CONTEXTE
# =====================================================

def clean_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(
    text: str,
    max_chars: int
) -> str:

    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]

    last_space = truncated.rfind(" ")

    if last_space > max_chars // 2:
        truncated = truncated[:last_space]

    return truncated.rstrip() + "..."


def build_context(documents: list) -> str:

    passages = []

    for index, doc in enumerate(
        documents[:MAX_DOCUMENTS],
        start=1
    ):
        content = clean_text(
            doc.get("content", "")
        )

        if not content:
            continue

        content = truncate_text(
            content,
            MAX_CHARS_PER_DOCUMENT
        )

        page = doc.get("page", "?")
        source = doc.get(
            "source",
            "Brochure EMSI"
        )

        passages.append(
            f"[DOCUMENT {index}]\n"
            f"Source : {source}\n"
            f"Page : {page}\n"
            f"Texte : {content}"
        )

    return "\n\n".join(passages)


# =====================================================
# PROMPT RAG STRICT
# =====================================================

def build_prompt(
    question: str,
    context: str
) -> str:

    return f"""Tu es EMSI-ChatBot, un assistant documentaire.

Ta mission est de répondre à la question de l'utilisateur
en utilisant EXCLUSIVEMENT les passages documentaires.

RÈGLES STRICTES :

1. Utilise uniquement les informations explicitement
   présentes dans les documents.

2. N'invente aucun nom de laboratoire, aucun équipement,
   aucun chiffre et aucune caractéristique.

3. Ne transforme jamais une formation, un diplôme,
   un enseignant, un club, une activité ou un partenariat
   en équipement.

4. Si la question porte sur les équipements,
   cite uniquement les équipements ou installations
   réellement mentionnés dans le contexte.

5. Si la question porte sur les laboratoires,
   cite uniquement les laboratoires réellement mentionnés.

6. Si le contexte indique un nombre de laboratoires,
   tu peux mentionner ce nombre avec sa page.

7. Si le contexte ne fournit pas de liste détaillée,
   indique clairement que cette liste n'est pas précisée.

8. N'utilise pas tes connaissances générales
   pour compléter les informations manquantes.

9. Chaque affirmation doit être justifiable par
   au moins un passage fourni.

10. Cite les pages utilisées sous la forme (page X).

11. Réponds en français simple, avec des phrases
    courtes, précises et grammaticalement complètes.

12. Ne répète pas les mêmes informations.

13. Si aucune information pertinente n'est disponible,
    réponds exactement :
    "Les documents consultés ne précisent pas cette information."

EXEMPLE DE DISTINCTION :
- "150 laboratoires modernes" : information sur
  les laboratoires.
- "Plateformes de simulation" : installation.
- "800 enseignants" : personnel, PAS équipement.
- "Diplôme d'ingénieur" : formation, PAS équipement.

DOCUMENTS :
{context}

QUESTION :
{question}

RÉPONSE FACTUELLE EN FRANÇAIS :
"""


# =====================================================
# GÉNÉRATION OLLAMA
# =====================================================

def generate_answer(
    question: str,
    documents: list
) -> str:

    question = clean_text(question)

    if not question:
        return "Veuillez poser une question."

    if not documents:
        return (
            "Je n'ai trouvé aucune information "
            "dans les documents EMSI."
        )

    context = build_context(documents)

    if not context:
        return (
            "Je n'ai trouvé aucun passage exploitable "
            "dans les documents EMSI."
        )

    prompt = build_prompt(
        question,
        context
    )

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT,
            "num_thread": NUM_THREADS,
            "temperature": 0.0,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        }
    }

    start = time.perf_counter()

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=(5, 150)
        )

        response.raise_for_status()
        data = response.json()

        answer = clean_text(
            data.get("response", "")
        )

        elapsed = time.perf_counter() - start

        load_seconds = (
            data.get("load_duration", 0) / 1e9
        )

        prompt_seconds = (
            data.get("prompt_eval_duration", 0) / 1e9
        )

        generation_seconds = (
            data.get("eval_duration", 0) / 1e9
        )

        logger.info(
            "Ollama total=%.2fs | "
            "chargement=%.2fs | "
            "prompt=%.2fs | "
            "generation=%.2fs",
            elapsed,
            load_seconds,
            prompt_seconds,
            generation_seconds
        )

        logger.info(
            "Tokens prompt=%s | "
            "tokens generes=%s",
            data.get("prompt_eval_count", 0),
            data.get("eval_count", 0)
        )

        if not answer:
            return (
                "Le modèle local n'a pas généré "
                "de réponse exploitable."
            )

        if data.get("done_reason") == "length":
            logger.warning(
                "Réponse limitée par num_predict=%s",
                NUM_PREDICT
            )

        return answer

    except requests.exceptions.Timeout as exc:
        logger.error(
            "Timeout Ollama : %s",
            exc
        )
        raise RuntimeError(
            "Le modèle local met trop de temps à répondre."
        ) from exc

    except requests.exceptions.ConnectionError as exc:
        logger.error(
            "Connexion Ollama impossible : %s",
            exc
        )
        raise RuntimeError(
            "Impossible de contacter Ollama."
        ) from exc

    except requests.exceptions.RequestException as exc:
        logger.error(
            "Erreur HTTP Ollama : %s",
            exc
        )
        raise RuntimeError(
            "Erreur de communication avec Ollama."
        ) from exc

    except ValueError as exc:
        logger.error(
            "JSON Ollama invalide : %s",
            exc
        )
        raise RuntimeError(
            "Réponse JSON Ollama invalide."
        ) from exc
