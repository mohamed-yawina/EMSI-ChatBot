
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")

for collection in ["emsi_text", "emsi_images"]:
    info = client.get_collection(collection)

    print(f"\nCollection : {collection}")
    print("Nombre de points :", client.count(
        collection_name=collection,
        exact=True
    ).count)

    points, _ = client.scroll(
        collection_name=collection,
        limit=1,
        with_payload=True,
        with_vectors=False
    )

    if points:
        print("Exemple de métadonnées :", points[0].payload)
