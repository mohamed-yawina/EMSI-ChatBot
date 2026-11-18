from app.rag.isolated_retriever import search_documents_isolated
from app.services.ollama_service import generate_answer

question = "Quelles sont les formations proposées par EMSI ?"

print("1. Recherche documentaire...")
documents = search_documents_isolated(question, limit=3)

print("2. Documents récupérés :")
for doc in documents:
    print(f"Page {doc['page']} - Score {doc['score']:.3f}")

print("3. Génération locale avec Qwen 1.5B...")
answer = generate_answer(question, documents)

print("\n=== RÉPONSE DU CHATBOT ===")
print(answer)
