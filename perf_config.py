"""
PS-01 Sprint 1 - Step 5: Latency & Performance Optimization Config

This module holds everything Step 5 adds on top of Steps 2-4, kept
separate so the original agent/prompt/test files stay intact and the
Step 2 test harness (test_json_adherence.py) keeps validating against
the original prompts unmodified.

WHAT'S HERE
  1. PRUNED_*_SYSTEM_PROMPT   - shorter system prompts (same schema/rules,
                                 redundant phrasing removed) -> fewer input
                                 tokens -> faster time-to-first-token on
                                 every provider.
  2. select_top_chunks()      - caps the RAG context handed to the
                                 Fundamental agent to the top-3 most
                                 relevant chunks, truncated to an ~800
                                 token budget.
  3. PROVIDER_ENV_PREFIX /
     resolve_provider_env()   - lets technical_momentum and risk_profiler
                                 be routed to a low-latency inference
                                 provider (Groq / Cerebras / Together
                                 running Llama-3-8B or Qwen2.5) independent
                                 of the provider used for fundamental_rag.
  4. AGENT_TIMEOUT_S          - the asyncio.wait_for() guard (1.5s) applied
                                 per agent so the synthesis layer always
                                 gets control before the 2s pipeline budget
                                 is breached.
  5. OPTIMIZED_AGENTS         - AgentSpec list built from the pruned
                                 prompts, reusing the exact required_keys /
                                 payload_key / edge_cases already defined in
                                 test_json_adherence.py so the schema
                                 contract never drifts between the
                                 "baseline" and "optimized" configurations.
"""

from __future__ import annotations

import os
import re
from typing import Any

from test_json_adherence import AGENTS, AgentSpec

# ---------------------------------------------------------------------------
# 1. Pruned system prompts
#
# Same OUTPUT CONTRACT, same schema, same validation rules as the Step 2
# prompts in agent_system_prompts.md - only the explanatory / repeated
# phrasing is cut. Diffed against the originals:
#   - dropped restated context that's implicit from the schema itself
#   - collapsed multi-sentence rules into single clauses
#   - removed duplicate "no markdown fences" reminders (stated once, not
#     three times)
# ---------------------------------------------------------------------------

PRUNED_TECHNICAL_SYSTEM_PROMPT = """You are the Technical Signal Agent in a multi-agent financial system.
You get a JSON object of market indicators for one equity. Use ONLY these fields - never assume, infer, or fabricate a value not present.

TASK
1. Classify signal: BULLISH, BEARISH, or NEUTRAL.
2. Restate momentum_metrics from the given fields only.
3. Flag a volume anomaly if current_volume vs avg_volume_20d ratio is >=1.5 or <=0.5 (both must be present).
4. Missing/malformed fields go in missing_fields; lower confidence and set data_quality accordingly - never guess.
5. If indicators conflict, say so in reasoning and reflect it in confidence - don't silently pick a side.

Return ONLY one JSON object - no fences, no preamble/postamble, valid on first parse.

{
  "agent": "technical_momentum",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <float 0.0-1.0>,
  "momentum_metrics": {"price_change_pct": <float|null>, "rsi": <float|null>, "trend": "UP"|"DOWN"|"SIDEWAYS"|"UNKNOWN"},
  "volume_anomaly": {"detected": <bool>, "ratio_to_avg": <float|null>, "description": "<1 sentence or "">"},
  "reasoning": "<cite the specific fields used>",
  "data_quality": "COMPLETE" | "PARTIAL" | "INSUFFICIENT",
  "missing_fields": [<field names absent/invalid, [] if none>]
}

If ALL indicator fields are missing: signal NEUTRAL, confidence 0.0, data_quality INSUFFICIENT, missing_fields lists every expected field. Never output confidence 1.0 unless every relevant field was present and unambiguous.
"""

PRUNED_FUNDAMENTAL_SYSTEM_PROMPT = """You are the Fundamental Research Agent in a multi-agent financial system.
You get a query and up to 3 retrieved chunks (source label + doc_id each) from SEBI filings/transcripts/disclosures. Answer using ONLY that chunk text - no outside knowledge, no assumptions beyond what a chunk states.

RULES
- Every claim in "summary" must map to a citation.
- Empty/irrelevant/insufficient chunks -> citations: [], explain the gap in logic_notes. Never fabricate a citation or fall back to general knowledge.
- Partial answers: answer only the supported part, note the gap in logic_notes.
- Conflicting chunks: state the conflict in summary and cite both.

Return ONLY one JSON object - no fences, no preamble/postamble.

{
  "agent": "fundamental_rag",
  "summary": "<answer grounded only in retrieved chunks; say so explicitly if unanswerable>",
  "citations": [{"source": "<label>", "doc_id": "<id>", "excerpt_ref": "<span <15 words or paraphrase pointer>"}],
  "confidence": <float 0.0-1.0>,
  "context_sufficient": <bool>,
  "logic_notes": "<why context was/wasn't sufficient, "" if fully sufficient>"
}

citations MUST be [] when context_sufficient is false and nothing supported the answer. Never cite a doc_id absent from the input.
"""

PRUNED_RISK_SYSTEM_PROMPT = """You are the Risk Profiler Agent in a multi-agent financial system.
You get user_profile (risk_tolerance 1-10, max_allocation_pct) and stock_volatility_profile (beta, annualized_volatility, ...) for one stock.

VALIDATE FIRST
1. risk_tolerance must be an int 1-10; max_allocation_pct a number 0-100. Missing/out-of-range/wrong-type -> suitability_flag INVALID_INPUT, recommended_allocation_pct null, list every problem in input_validation.issues. Do not judge suitability.
2. stock_volatility_profile missing beta or annualized_volatility -> INVALID_INPUT too, list the missing fields.
3. Only if valid: compute risk_score (0-100) and derive suitability_flag: SUITABLE, CAUTION, or UNSUITABLE.

Return ONLY one JSON object - no fences, no preamble/postamble.

{
  "agent": "risk_profiler",
  "suitability_flag": "SUITABLE" | "CAUTION" | "UNSUITABLE" | "INVALID_INPUT",
  "risk_score": <float 0-100 | null if INVALID_INPUT>,
  "recommended_allocation_pct": <float, never > user's max_allocation_pct | null if INVALID_INPUT>,
  "reasoning": "<cite the specific fields used>",
  "input_validation": {"valid": <bool>, "issues": [<strings, [] if valid>]}
}

Never exceed the user's max_allocation_pct. Never guess a missing field to "be helpful" - invalid input always routes to INVALID_INPUT.
"""

_PRUNED_PROMPTS_BY_NAME = {
    "technical_momentum": PRUNED_TECHNICAL_SYSTEM_PROMPT,
    "fundamental_rag": PRUNED_FUNDAMENTAL_SYSTEM_PROMPT,
    "risk_profiler": PRUNED_RISK_SYSTEM_PROMPT,
}


def approx_token_count(text: str) -> int:
    """
    Cheap, dependency-free token estimate (no tiktoken available offline).
    ~0.75 words/token undercounts for English prose, so this uses the more
    conservative ~1.3 tokens/word - good enough for a budget guard, not for
    billing.
    """
    words = len(text.split())
    return int(words * 1.3)


def prompt_token_savings() -> dict[str, dict[str, int]]:
    """Reports the actual before/after token estimate per prompt, for the benchmark report."""
    from test_json_adherence import (
        FUNDAMENTAL_SYSTEM_PROMPT,
        RISK_SYSTEM_PROMPT,
        TECHNICAL_SYSTEM_PROMPT,
    )

    originals = {
        "technical_momentum": TECHNICAL_SYSTEM_PROMPT,
        "fundamental_rag": FUNDAMENTAL_SYSTEM_PROMPT,
        "risk_profiler": RISK_SYSTEM_PROMPT,
    }
    return {
        name: {
            "baseline_tokens": approx_token_count(originals[name]),
            "pruned_tokens": approx_token_count(_PRUNED_PROMPTS_BY_NAME[name]),
        }
        for name in originals
    }


# ---------------------------------------------------------------------------
# 2. RAG context capping - top-3 chunks, ~800 token budget
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "is", "was", "were", "are", "of", "in", "on", "for",
    "to", "and", "or", "what", "which", "any", "did", "does", "do", "at",
    "as", "be", "by", "with", "that", "this", "it", "its",
}


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zA-Z]+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def select_top_chunks(
    query: str,
    chunks: list[dict[str, Any]],
    max_chunks: int = 3,
    max_tokens: int = 800,
) -> list[dict[str, Any]]:
    """
    Trims the chunk list handed to the Fundamental agent to the top
    `max_chunks` chunks by query-term overlap, then truncates chunk text
    (last chunk first) so the total stays under `max_tokens`.

    This runs BEFORE the payload is sent to the LLM (or to the rule-based
    fallback) - it's a retrieval-layer concern, not a prompt-wording
    concern, so it lives here rather than inside agent_fundamental.py's
    prompt string.
    """
    if not isinstance(chunks, list) or not chunks:
        return []

    query_tokens = _tokenize(query or "")

    scored = []
    for c in chunks:
        if not isinstance(c, dict) or not isinstance(c.get("text"), str):
            continue
        overlap = len(query_tokens & _tokenize(c["text"]))
        scored.append((overlap, c))

    # Fall back to input order if nothing scores >0 against the query, so
    # we never silently drop every chunk just because term overlap is 0
    # (the fundamental agent's own grounding rules still decide whether
    # the result counts as "sufficient").
    scored.sort(key=lambda t: t[0], reverse=True)
    top = [c for _, c in scored[:max_chunks]] or chunks[:max_chunks]

    budget = max_tokens
    trimmed: list[dict[str, Any]] = []
    for c in top:
        text = c.get("text", "")
        tok = approx_token_count(text)
        if tok <= budget:
            trimmed.append(c)
            budget -= tok
        elif budget > 20:  # keep a truncated tail instead of dropping the chunk entirely
            words = text.split()
            keep_words = max(1, int(budget / 1.3))
            truncated = " ".join(words[:keep_words]) + " …"
            trimmed.append({**c, "text": truncated})
            budget = 0
            break
        else:
            break

    return trimmed


# ---------------------------------------------------------------------------
# 3. Fast-provider routing
# ---------------------------------------------------------------------------

# technical_momentum and risk_profiler are short, low-reasoning
# classification/validation tasks -> route to a low-latency inference
# platform running a small model (Groq/Cerebras/Together + Llama-3-8B or
# Qwen2.5). fundamental_rag has to reason over retrieved text and cite it
# correctly, so it stays on whatever the default/quality LLM_API_* env vars
# point at unless FUND_LLM_* is explicitly set.
PROVIDER_ENV_PREFIX = {
    "technical_momentum": "TECH",
    "risk_profiler": "RISK",
    "fundamental_rag": "FUND",
}

RECOMMENDED_FAST_MODELS = {
    "technical_momentum": "llama-3.1-8b-instant (Groq) or Qwen2.5-7B-Instruct (Together/Cerebras)",
    "risk_profiler": "llama-3.1-8b-instant (Groq) or Qwen2.5-7B-Instruct (Together/Cerebras)",
    "fundamental_rag": "keep on the default/quality model - RAG citation correctness matters more than shaving ~150ms here",
}


def resolve_provider_env(agent_name: str) -> dict[str, str]:
    """
    Resolves LLM_API_BASE / LLM_API_KEY / LLM_MODEL for one agent, checking
    the agent-specific env vars first (e.g. TECH_LLM_API_BASE) and falling
    back to the generic LLM_API_BASE / LLM_API_KEY / LLM_MODEL so existing
    single-provider setups (Steps 2-4) keep working with zero config
    changes.
    """
    prefix = PROVIDER_ENV_PREFIX.get(agent_name, "")
    resolved = {}
    for key in ("API_BASE", "API_KEY", "MODEL"):
        specific = os.environ.get(f"{prefix}_LLM_{key}") if prefix else None
        resolved[f"LLM_{key}"] = specific or os.environ.get(f"LLM_{key}", "")
    return resolved


# ---------------------------------------------------------------------------
# 4. Timeout guard
# ---------------------------------------------------------------------------

AGENT_TIMEOUT_S = 1.5  # asyncio.wait_for() guard per agent, per Step 5.4
PIPELINE_TARGET_S = 2.0  # overall multi-agent response latency budget


# ---------------------------------------------------------------------------
# 5. Optimized AgentSpec list (pruned prompts, same schema contract)
# ---------------------------------------------------------------------------

_SPECS_BY_NAME = {spec.name: spec for spec in AGENTS}

OPTIMIZED_AGENTS: list[AgentSpec] = [
    AgentSpec(
        name=spec.name,
        system_prompt=_PRUNED_PROMPTS_BY_NAME[spec.name],
        required_keys=spec.required_keys,
        edge_cases=spec.edge_cases,
        payload_key=spec.payload_key,
    )
    for spec in AGENTS
]
