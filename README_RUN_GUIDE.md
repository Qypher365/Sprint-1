# How to Run This — PS-01 Execution Lead Setup

## 0. Folder structure (should look like this after unzipping)

```
project/
├── data/
│   ├── tata_motors_feed.json
│   ├── reliance_feed.json
│   └── infosys_feed.json
├── sebi_corpus/
│   ├── sebi_disclosure_01_tatamotors_q1fy27_results.txt
│   └── sebi_disclosure_02_reliance_material_event.txt
├── mock_market_service.py
├── ingest_sebi_docs.py
├── query_sebi_docs.py
└── requirements.txt
```

## 1. One-time setup (do this today, not on demo day)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The first `sentence-transformers` install downloads a small embedding model
(~90MB) — needs internet once. After that, everything runs fully offline,
which matters if the venue wifi is bad.

## 2. Ingest the SEBI docs into Chroma (one-time, before the demo)

```bash
python ingest_sebi_docs.py
```

Expected output: `Ingested N chunks from 2 filings into 'sebi_disclosures'.`
This creates a `chroma_store/` folder — that folder IS your vector DB.
Copy the whole `chroma_store/` folder to whatever laptop actually runs the
demo, so you never have to re-embed live on stage.

**Sanity check it worked:**
```bash
python query_sebi_docs.py "reliance margin pressure petrochemical"
```
You should see the Reliance Regulation 30 filing come back as the top hit,
with its section name. That section + distance score is what your
sentiment agent should surface to the user as its citation.

## 3. Start the mock market feed service

```bash
uvicorn mock_market_service:app --reload --port 8001
```

**Test it's alive:**
```bash
curl http://localhost:8001/symbols
curl http://localhost:8001/feed/reliance
curl http://localhost:8001/feed/infosys
```
`infosys` will come back with `"data_feed_status": "DEGRADED"` and a
`sentiment.classification` of `"UNAVAILABLE"` — that's your degraded-data
trigger, already built into the data, no extra flag needed.

Add `?jitter=true` (e.g. `/feed/reliance?jitter=true`) if you want the
price numbers to move slightly each time you re-run live on stage, so it
doesn't look like a static screenshot.

## 4. Wiring this into your teammates' agents (CrewAI/LangChain)

Whoever owns the agent orchestration should call:
- `GET http://localhost:8001/feed/{symbol}` instead of a real market data
  API — same shape, so swapping in a real feed later is a one-line change.
- The Chroma collection `sebi_disclosures` (already persisted in
  `chroma_store/`) directly via `chromadb.PersistentClient`, the same way
  `query_sebi_docs.py` does it — for the RAG agent's grounding step.

Give them this snippet to drop into their agent's tool functions:

```python
import requests
def get_market_feed(symbol: str) -> dict:
    return requests.get(f"http://localhost:8001/feed/{symbol}").json()
```

```python
import chromadb
from chromadb.utils import embedding_functions

_client = chromadb.PersistentClient(path="./chroma_store")
_embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
_collection = _client.get_collection("sebi_disclosures", embedding_function=_embed_fn)

def retrieve_disclosure_context(query: str, top_k: int = 2) -> list[dict]:
    results = _collection.query(query_texts=[query], n_results=top_k)
    return [
        {"text": doc, "source": meta["source"], "section": meta["section"]}
        for doc, meta in zip(results["documents"][0], results["metadatas"][0])
    ]
```

## 5. Full dry run order (matches the demo script)

1. Terminal 1: `uvicorn mock_market_service:app --reload --port 8001` (leave running)
2. Confirm `chroma_store/` exists (from step 2) and is on the demo laptop
3. Whatever frontend/orchestrator you built points at `localhost:8001` and
   `./chroma_store` — start that
4. Walk through `60_second_demo_script.md` end to end, phone stopwatch running
5. If anything is flaky, record a screen capture of a clean run as backup —
   per the checklist in the demo script

## Common gotchas

- **"Collection not found" error in query_sebi_docs.py** → you skipped step 2,
  or ran it from a different working directory. Chroma path is relative to
  wherever you run the script from.
- **CORS errors from a browser frontend** → already handled, CORS is wide
  open in `mock_market_service.py`; if you still see it, check you're
  hitting `localhost:8001` not `127.0.0.1:8001` (some browsers treat these
  as different origins for CORS).
- **Demo laptop has no internet on the day** → fine, as long as you ran
  step 1 and step 2 ahead of time and copied `chroma_store/` + the `venv`
  (or just reinstall requirements once beforehand) onto that machine.
