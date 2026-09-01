"""
Example retrieval call — this is what your sentiment/RAG agent should do
internally, and it's the pattern that produces the "attribution visible to
the user" requirement in the problem statement.

Run:
    python query_sebi_docs.py "reliance margin pressure petrochemical"
"""

import sys
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CHROMA_DIR = Path(__file__).parent / "chroma_store"
COLLECTION_NAME = "sebi_disclosures"


def query(question: str, top_k: int = 2):
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_collection(COLLECTION_NAME, embedding_function=embedding_fn)

    results = collection.query(query_texts=[question], n_results=top_k)

    print(f"\nQuery: {question}\n")
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        print("-" * 60)
        print(f"SOURCE: {meta['source']}  |  SECTION: {meta['section']}  |  distance: {dist:.3f}")
        print(doc[:400] + ("..." if len(doc) > 400 else ""))
    print("-" * 60)


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "margin pressure and risk factors"
    query(q)
