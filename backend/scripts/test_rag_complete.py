
import gc
import requests

from app.rag.retriever import search_documents, get_embedding_model

QUESTION = "Quelles sont les filières proposées par l'EMSI ?"

print("1. Recherche documentaire...")
documents = search_documents(QUESTION, limit=5)

for doc in documents:
    print(f"Page {doc['page']} - Score {doc['score']:.3f}")

print("\n2. Libération du modèle BGE-M3...")
get_embedding_model.cache_clear()
gc.collect()

print("\n3. Génération avec Ollama...")

context = "\n\n".join(
    f"[Page {doc['page']}]\n{doc['content']}"
    for doc in documents
)

prompt = f"""
Tu es EMSI-ChatBot, assistant de l'EMSI.

Réponds uniquement avec les informations du contexte.
Si le contexte ne permet pas de répondre, dis-le clairement.
Cite les numéros de page quand c'est possible.

CONTEXTE :
{context}

QUESTION :
{QUESTION}

RÉPONSE EN FRANÇAIS :
"""

response = requests.post(
    "http://127.0.0.1:11434/api/generate",
    json={
        "model": "qwen2.5:3b",
        "prompt": prompt,
        "stream": False,
        "keep_alive": "0s",
        "options": {
            "temperature": 0.1,
            "num_ctx": 2048,
            "num_predict": 250,
        },
    },
    timeout=180,
)

response.raise_for_status()

print("\n=== RÉPONSE DU CHATBOT ===")
print(response.json()["response"])
