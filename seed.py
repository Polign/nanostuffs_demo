"""Load the sample handbook into Qdrant with a multilingual embedder.

Stands in for the Nanostuffs document pipeline. Swap the embedder for the
multilingual model you already use; nothing in chat.py depends on which one.
"""
import json
import os
import sys

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("HANDBOOK_COLLECTION", "handbook")
EMBEDDER = os.environ.get("EMBEDDER", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "handbook.json")) as f:
        chunks = json.load(f)
    embedder = TextEmbedding(EMBEDDER)
    vectors = list(embedder.embed([c["title"] + "\n" + c["text"] for c in chunks]))
    client = QdrantClient(url=QDRANT_URL, api_key=os.environ.get("QDRANT_API_KEY"))
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=models.VectorParams(
        size=len(vectors[0]), distance=models.Distance.COSINE))
    client.upsert(COLLECTION, points=[
        models.PointStruct(id=c["id"], vector=v.tolist(), payload=c) for c, v in zip(chunks, vectors)])
    print(f"seeded {len(chunks)} chunks into {QDRANT_URL} collection {COLLECTION!r} with {EMBEDDER}", file=sys.stderr)


if __name__ == "__main__":
    main()
