"""
SEBI Disclosure Ingestion — for Shlok's vector DB (Chroma)

Chunks the two synthetic SEBI .txt filings by section/paragraph and loads
them into a local, persistent Chroma collection. Uses sentence-transformers
locally (all-MiniLM-L6-v2) so this works with NO API key and NO internet
during the actual demo — only this ingestion step needs internet once, to
download the embedding model.

Run ONCE before the demo (not live on stage):
    python ingest_sebi_docs.py

This creates a folder ./chroma_store with the persisted DB. Commit that
folder or re-run this script on the demo machine ahead of time.
"""

import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CORPUS_DIR = Path(__file__).parent / "sebi_corpus"
CHROMA_DIR = Path(__file__).parent / "chroma_store"
COLLECTION_NAME = "sebi_disclosures"


def chunk_text(raw_text: str, source_filename: str) -> list[dict]:
    """Split each filing into section-level chunks using the ALL-CAPS
    'SECTION N —' headers already present in the synthetic filings.
    Falls back to paragraph splitting if no section headers are found."""
    sections = re.split(r"\n(?=SECTION \d+ —)", raw_text)
    chunks = []
    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue
        header_match = re.match(r"SECTION \d+ — ([^\n]+)", section)
        section_title = header_match.group(1) if header_match else f"Part {i+1}"
        chunks.append(
            {
                "text": section,
                "metadata": {
                    "source": source_filename,
                    "section": section_title,
                },
            }
        )
    return chunks


def main():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # Fresh collection each run so re-ingesting doesn't create duplicates
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME, embedding_function=embedding_fn
    )

    all_ids, all_docs, all_metas = [], [], []
    for txt_path in sorted(CORPUS_DIR.glob("*.txt")):
        raw_text = txt_path.read_text(encoding="utf-8")
        chunks = chunk_text(raw_text, txt_path.name)
        for idx, chunk in enumerate(chunks):
            all_ids.append(f"{txt_path.stem}__chunk{idx}")
            all_docs.append(chunk["text"])
            all_metas.append(chunk["metadata"])

    collection.add(ids=all_ids, documents=all_docs, metadatas=all_metas)
    print(f"Ingested {len(all_ids)} chunks from {len(list(CORPUS_DIR.glob('*.txt')))} filings into '{COLLECTION_NAME}'.")


if __name__ == "__main__":
    main()
