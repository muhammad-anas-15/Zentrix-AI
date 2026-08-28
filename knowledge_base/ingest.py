"""
Ingests knowledge_base/source_docs/trading_knowledge.json into a local
Chroma vector database. Uses a free, local embedding model
(sentence-transformers) — no API cost, runs offline.

Run once (or whenever trading_knowledge.json is updated):
    python knowledge_base/ingest.py
"""
import os
import json
import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_FILE = os.path.join(BASE_DIR, "source_docs", "trading_knowledge.json")
VECTOR_STORE_DIR = os.path.join(BASE_DIR, "vector_store")
COLLECTION_NAME = "trading_knowledge"

EMBED_MODEL = "all-MiniLM-L6-v2"  # free, local, ~80MB, good quality for short text


def load_knowledge(path: str = SOURCE_FILE) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ingest():
    os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=VECTOR_STORE_DIR)

    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )

    # Reset collection each ingest run so updates to trading_knowledge.json
    # are reflected cleanly (no stale/duplicate entries)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME, embedding_function=embed_fn
    )

    entries = load_knowledge()
    ids = [e["id"] for e in entries]
    documents = [f"{e['title']}: {e['content']}" for e in entries]
    metadatas = [{"category": e["category"], "title": e["title"]} for e in entries]

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"Ingested {len(entries)} knowledge entries into '{COLLECTION_NAME}' "
          f"at {VECTOR_STORE_DIR}")


if __name__ == "__main__":
    ingest()