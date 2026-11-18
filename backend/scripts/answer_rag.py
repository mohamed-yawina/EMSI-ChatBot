
import sys

import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434/api/generate"

TEXT_COLLECTION = "emsi_text"
EMBEDDING_MODEL = "BAAI/bge-m3"
LLM_MODEL = "qwen2.5:3b"

TOP_K = 8


def retrieve_context(question):
    print("\nRecherche dans la brochure EMSI...")

    bge = SentenceTransformer(
        EMBEDDING_MODEL,
        device="cpu"
    )

    vector = bge.encode(
        question,
        normalize_embeddings=True
    )

    client = QdrantClient(
        url=QDRANT_URL,
        timeout=60
    )

    results = client.query_points(
        collection_name=TEXT_COLLECTION,
        query=vector.tolist(),
        limit=TOP_K,
        with_payload=True
    ).points

    passages = []

    for result in results:
        payload = result.payload or {}
        content = payload.get("content", "").strip()

        if not content:
            continue

        passages.append({
            "content": content,
            "page": payload.get("page", "?"),
            "source": payload.get("source", "Document EMSI")
        })

    return passages


def generate_answer(question, passages):
    if not passages:
        return "Je n'ai trouvé aucune information dans la brochure EMSI."

    context = "\n\n".join(
        f"[Source {i} - {item['source']}, page {item['page']}]\n"
        f"{item['content']}"
        for i, item in enumerate(passages, start=1)
    )

    prompt = f"""
Tu es EMSI-ChatBot, un assistant qui répond aux questions
sur l'École Marocaine des Sciences de l'Ingénieur (EMSI).

RÈGLES :
- Réponds uniquement à partir du CONTEXTE DOCUMENTAIRE.
- Réponds en français clair et simple.
- N'invente aucune information.
- Si le contexte est insuffisant, dis-le clairement.
- Cite les pages du document qui justifient ta réponse.
- Ne cite pas une page qui ne contient pas l'information.
- Si la question demande une liste complète, ne prétends pas
  qu'elle est exhaustive si le contexte ne le permet pas.

CONTEXTE DOCUMENTAIRE :
{context}

QUESTION :
{question}

RÉPONSE :
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": LLM_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 500
            }
        },
        timeout=300
    )

    response.raise_for_status()

    return response.json().get("response", "").strip()


def main():
    question = " ".join(sys.argv[1:]).strip()

    if not question:
        question = input("Question : ").strip()

    if not question:
        raise ValueError("La question est vide.")

    passages = retrieve_context(question)

    print(f"\n{len(passages)} passages récupérés.")

    print("\nGénération avec Ollama...")

    answer = generate_answer(question, passages)

    print("\n========== RÉPONSE EMSI-CHATBOT ==========")
    print(answer)

    print("\n========== SOURCES RÉCUPÉRÉES ==========")

    for item in passages:
        print(f"- {item['source']} — page {item['page']}")


if __name__ == "__main__":
    main()
