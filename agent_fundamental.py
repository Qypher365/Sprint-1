"""
PS-01 Sprint 1 - Fundamental / RAG Grounding Agent

Implements the "Fundamental Research Agent" described in Step 2. Answers a
query using ONLY retrieved document chunks, with every claim traceable to a
citation, and an explicit "insufficient context" path instead of ever
answering from outside knowledge.

Run standalone:
    python agent_fundamental.py
"""

from __future__ import annotations

import re
from typing import Any

from agent_base import BaseAgent

FUNDAMENTAL_SYSTEM_PROMPT = """You are the Fundamental Research Agent in a multi-agent financial intelligence
system. You are given (a) a user's natural-language query and (b) a list of
retrieved document chunks from a semantic search layer over SEBI filings,
earnings transcripts, and disclosures. Each chunk has a source label and doc_id.

TASK
Produce a factual summary that answers the query using ONLY the retrieved
chunk text. You are strictly forbidden from using outside knowledge, prior
training data about the company, or assumptions not directly supported by a
retrieved chunk.

GROUNDING RULES
1. Every factual claim in "summary" must map to at least one entry in "citations".
2. If the retrieved chunks are empty, irrelevant, or insufficient, you MUST set
   "citations": [] and explain the gap in "logic_notes". Do not fabricate a
   citation, and do not answer from general knowledge as a fallback.
3. If chunks partially answer the query, answer only the supported part and use
   "logic_notes" to state what remains unanswered.
4. If chunks conflict, report the conflict in "summary" and cite both.

OUTPUT CONTRACT
Return ONLY a single JSON object. No markdown code fences, no backticks, no
preamble, no postamble.

Schema (all keys required):
{
  "agent": "fundamental_rag",
  "summary": "<factual answer grounded only in retrieved chunks; state explicitly if unanswerable>",
  "citations": [
    {"source": "<source label from chunk>", "doc_id": "<doc_id from chunk>", "excerpt_ref": "<short quoted span under 15 words or paraphrase pointer>"}
  ],
  "confidence": <float 0.0-1.0>,
  "context_sufficient": <boolean>,
  "logic_notes": "<why context was/was not sufficient, or empty string if fully sufficient>"
}

RULES
- citations MUST be [] whenever context_sufficient is false AND no chunk supported
  any part of the answer.
- Never cite a doc_id that was not present in the input chunk list.
- Never wrap the JSON in ```json or any other formatting.
"""

_STOPWORDS = {
    "the", "a", "an", "is", "was", "were", "are", "of", "in", "on", "for",
    "to", "and", "or", "what", "which", "any", "did", "does", "do", "at",
    "as", "be", "by", "with", "that", "this", "it", "its",
}


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z]+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


class FundamentalRagAgent(BaseAgent):
    name = "fundamental_rag"
    system_prompt = FUNDAMENTAL_SYSTEM_PROMPT
    payload_key = "rag_input"
    required_keys = {"agent", "summary", "citations", "confidence", "context_sufficient", "logic_notes"}

    def _insufficient(self, logic_notes: str) -> dict[str, Any]:
        return {
            "agent": self.name,
            "summary": "Insufficient retrieved context to answer the query.",
            "citations": [],
            "confidence": 0.0,
            "context_sufficient": False,
            "logic_notes": logic_notes,
        }

    def run_rule_based(self, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}
        query = data.get("query")
        chunks = data.get("chunks")

        if not isinstance(query, str) or not query.strip():
            return self._insufficient("No usable natural-language query was provided.")
        if not isinstance(chunks, list) or not chunks:
            return self._insufficient("No retrieved chunks were provided (empty or wrong type).")

        query_tokens = _tokenize(query)

        usable, excluded_metadata = [], []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                excluded_metadata.append("a chunk was not an object and was excluded")
                continue
            source = chunk.get("source")
            doc_id = chunk.get("doc_id")
            text = chunk.get("text")
            if not (isinstance(source, str) and source.strip()):
                excluded_metadata.append(f"a chunk (doc_id={doc_id!r}) lacked a valid 'source' and was excluded from citation")
                continue
            if not (isinstance(doc_id, str) and doc_id.strip()):
                excluded_metadata.append(f"a chunk (source={source!r}) lacked a valid 'doc_id' and was excluded from citation")
                continue
            if not isinstance(text, str) or not text.strip():
                excluded_metadata.append(f"chunk {doc_id} had no text content and was excluded")
                continue
            usable.append({"source": source, "doc_id": doc_id, "text": text})

        if not usable:
            note = "No chunk had the required source/doc_id/text metadata to be cited."
            if excluded_metadata:
                note += " " + " ".join(excluded_metadata)
            return self._insufficient(note)

        # Relevance scoring: token overlap between query and chunk text.
        scored = []
        for c in usable:
            overlap = len(query_tokens & _tokenize(c["text"]))
            scored.append((overlap, c))
        scored.sort(key=lambda t: t[0], reverse=True)

        relevant = [c for score, c in scored if score > 0]
        if not relevant:
            note = "None of the retrieved chunks shared relevant terms with the query."
            if excluded_metadata:
                note += " " + " ".join(excluded_metadata)
            return self._insufficient(note)

        # Detect potential numeric conflicts among relevant chunks (same-ish
        # topic, different numbers) — a cheap heuristic, not full NLI.
        numeric_by_chunk = [(c, re.findall(r"\d+(?:\.\d+)?%?", c["text"])) for c in relevant]
        conflict_flag = len(relevant) > 1 and len({tuple(n) for _, n in numeric_by_chunk if n}) > 1

        citations = [
            {"source": c["source"], "doc_id": c["doc_id"], "excerpt_ref": " ".join(c["text"].split()[:15])}
            for c in relevant
        ]

        summary_sentences = []
        for c in relevant:
            first_sentence = re.split(r"(?<=[.!?])\s", c["text"].strip())[0]
            summary_sentences.append(f"Per {c['source']} ({c['doc_id']}): {first_sentence}")
        summary = " ".join(summary_sentences)
        if conflict_flag:
            summary = "Retrieved sources report differing figures for this query. " + summary

        logic_notes = ""
        if excluded_metadata:
            logic_notes = " ".join(excluded_metadata)

        confidence = round(min(0.9, 0.4 + 0.15 * len(relevant)), 2)
        if conflict_flag:
            confidence = round(confidence * 0.6, 2)

        return {
            "agent": self.name,
            "summary": summary,
            "citations": citations,
            "confidence": confidence,
            "context_sufficient": True,
            "logic_notes": logic_notes,
        }


if __name__ == "__main__":
    import json as _json

    agent = FundamentalRagAgent()
    samples = [
        {"query": "What was the company's Q2 revenue growth?",
         "chunks": [{"source": "Q2 Earnings Transcript", "doc_id": "EARN-2026-Q2-001", "text": "Revenue grew 18% YoY to INR 4,200 crore in Q2 FY26."}]},
        {"query": "What was the company's Q2 revenue growth?", "chunks": []},
        {"query": "What is the promoter shareholding percentage?",
         "chunks": [{"source": "Shareholding Q1", "doc_id": "SHP-Q1-26", "text": "Promoter holding stands at 54.2% as of Q1."},
                    {"source": "Shareholding Q2", "doc_id": "SHP-Q2-26", "text": "Promoter holding stands at 49.8% as of Q2."}]},
    ]
    for s in samples:
        print(f"\ninput: {s}")
        print(_json.dumps(agent.run(s, mode="rule"), indent=2))
