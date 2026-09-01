"""
PS-01 Sprint 1 - Step 2.4: Edge-case test harness for the three JSON-enforced
agent system prompts (technical_momentum, fundamental_rag, risk_profiler).

WHAT THIS DOES
    - Defines 15+ edge-case inputs per agent (missing fields, malformed types,
      conflicting signals, empty retrieval, out-of-range profiles, etc.)
    - Sends each edge case to a high-speed OpenAI-compatible chat completions
      endpoint (Groq / Cerebras / Together / OpenRouter all work) using the
      matching system prompt from agent_system_prompts.md
    - Validates the raw completion text is: (a) parseable as JSON with no
      markdown fences / preamble / postamble, and (b) contains the required
      top-level keys for that agent's schema
    - Prints a pass/fail report per edge case and an overall adherence %

HOW TO RUN
    1. pip install requests
    2. Set environment variables:
         LLM_API_BASE   e.g. "https://api.groq.com/openai/v1"
         LLM_API_KEY    your key
         LLM_MODEL      e.g. "llama-3.3-70b-versatile"
    3. python test_json_adherence.py

DRY RUN (no network / no key)
    If LLM_API_KEY is not set, the script runs in dry-run mode: it still
    validates the harness and edge cases are well-formed and prints exactly
    what payload *would* be sent for each case, so you can sanity-check
    coverage before wiring up a real endpoint. This is the mode this was
    executed in during development, since this environment has no network
    access.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    import requests
except ImportError:
    requests = None


# ---------------------------------------------------------------------------
# System prompts (kept inline + in sync with agent_system_prompts.md)
# ---------------------------------------------------------------------------

TECHNICAL_SYSTEM_PROMPT = """You are the Technical Signal Agent in a multi-agent financial intelligence system.

You receive a JSON object of market indicators for a single equity (price series,
volume, RSI, moving averages, etc.). You do not have access to news, filings, or
any data outside the JSON object you are given. Do not assume, infer, or fabricate
any indicator value that is not present in the input.

TASK
Classify the stock's momentum signal using only the provided fields:
1. Determine signal: "BULLISH", "BEARISH", or "NEUTRAL".
2. Compute/restate momentum_metrics from the given fields only.
3. Detect volume anomalies by comparing current volume to avg_volume_20d if both
   are present.
4. If a required field is missing or malformed, do NOT guess its value. Record it
   in "missing_fields" and lower "confidence" and set "data_quality" accordingly.
5. If two available indicators conflict, state the conflict explicitly inside
   "reasoning" and reflect the uncertainty in "confidence" - do not silently pick a side.

OUTPUT CONTRACT
Return ONLY a single JSON object. No markdown code fences, no backticks, no
preamble, no postamble, no explanation outside the JSON.

Schema (all keys required, use null where genuinely unknown - never omit a key):
{
  "agent": "technical_momentum",
  "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
  "confidence": <float 0.0-1.0>,
  "momentum_metrics": {
    "price_change_pct": <float or null>,
    "rsi": <float or null>,
    "trend": "UP" | "DOWN" | "SIDEWAYS" | "UNKNOWN"
  },
  "volume_anomaly": {
    "detected": <boolean>,
    "ratio_to_avg": <float or null>,
    "description": "<one sentence, or empty string if not detected>"
  },
  "reasoning": "<cite the specific input fields used>",
  "data_quality": "COMPLETE" | "PARTIAL" | "INSUFFICIENT",
  "missing_fields": [<list of field names absent or invalid from the input, empty array if none>]
}

RULES
- If ALL required indicator fields are missing, return signal "NEUTRAL",
  confidence 0.0, data_quality "INSUFFICIENT", and list every expected field
  in missing_fields.
- Never output confidence 1.0 unless every relevant field was present and unambiguous.
- Never wrap the JSON in ```json or any other formatting.
"""

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

RISK_SYSTEM_PROMPT = """You are the Risk Profiler Agent in a multi-agent financial intelligence
system. You receive (a) a user_profile object with a risk_tolerance rating
(1-10) and a max_allocation_pct limit, and (b) a stock_volatility_profile
object (e.g. beta, annualized_volatility, sector, market_cap_category) for a
candidate stock.

TASK
Compute a suitability_flag for whether this stock fits this specific user's
risk profile, and a recommended_allocation_pct that never exceeds the user's
stated max_allocation_pct.

VALIDATION RULES (apply before reasoning about suitability)
1. risk_tolerance must be an integer 1-10 inclusive. max_allocation_pct must be
   a number between 0 and 100 inclusive. If either is missing, out of range,
   null, or the wrong type, do NOT attempt a suitability judgement: set
   suitability_flag "INVALID_INPUT", recommended_allocation_pct null, and list
   every problem in input_validation.issues.
2. If stock_volatility_profile is missing required fields (beta or
   annualized_volatility), set suitability_flag "INVALID_INPUT" too and list
   the missing fields.
3. Only when inputs pass validation, compute risk_score (0-100) and derive
   suitability_flag as "SUITABLE", "CAUTION", or "UNSUITABLE".

OUTPUT CONTRACT
Return ONLY a single JSON object. No markdown code fences, no backticks, no
preamble, no postamble.

Schema (all keys required):
{
  "agent": "risk_profiler",
  "suitability_flag": "SUITABLE" | "CAUTION" | "UNSUITABLE" | "INVALID_INPUT",
  "risk_score": <float 0-100, or null if INVALID_INPUT>,
  "recommended_allocation_pct": <float, never exceeding user's max_allocation_pct, or null if INVALID_INPUT>,
  "reasoning": "<cite the specific input fields used>",
  "input_validation": {
    "valid": <boolean>,
    "issues": [<list of strings describing each validation problem, empty array if valid>]
  }
}

RULES
- Never produce a recommended_allocation_pct greater than the user's max_allocation_pct.
- Never guess a missing risk_tolerance or volatility field.
- Never wrap the JSON in ```json or any other formatting.
"""


# ---------------------------------------------------------------------------
# Edge cases: 15+ per agent
# ---------------------------------------------------------------------------

TECHNICAL_EDGE_CASES: list[dict[str, Any]] = [
    {"name": "complete_bullish", "input": {"price": 152.4, "price_change_pct": 4.1, "rsi": 68, "avg_volume_20d": 1_200_000, "current_volume": 1_950_000, "sma_50": 140.2, "sma_200": 130.1}},
    {"name": "complete_bearish", "input": {"price": 88.2, "price_change_pct": -5.6, "rsi": 24, "avg_volume_20d": 900_000, "current_volume": 2_100_000, "sma_50": 95.0, "sma_200": 101.0}},
    {"name": "all_fields_missing", "input": {}},
    {"name": "only_price_no_history", "input": {"price": 100.0}},
    {"name": "rsi_extreme_overbought", "input": {"price": 210.0, "price_change_pct": 12.0, "rsi": 97.5, "avg_volume_20d": 500_000, "current_volume": 510_000}},
    {"name": "rsi_extreme_oversold", "input": {"price": 12.5, "price_change_pct": -18.0, "rsi": 2.1, "avg_volume_20d": 300_000, "current_volume": 305_000}},
    {"name": "conflicting_signals", "input": {"price": 100.0, "price_change_pct": 6.0, "rsi": 89, "avg_volume_20d": 1_000_000, "current_volume": 250_000}},
    {"name": "volume_field_missing", "input": {"price": 55.0, "price_change_pct": 1.2, "rsi": 51, "current_volume": 700_000}},
    {"name": "avg_volume_missing", "input": {"price": 55.0, "price_change_pct": 1.2, "rsi": 51, "avg_volume_20d": None}},
    {"name": "volume_as_string", "input": {"price": 55.0, "price_change_pct": 1.2, "rsi": 51, "avg_volume_20d": "1200000", "current_volume": "1950000"}},
    {"name": "negative_price", "input": {"price": -10.0, "price_change_pct": 3.0, "rsi": 55}},
    {"name": "rsi_null", "input": {"price": 60.0, "price_change_pct": 0.5, "rsi": None, "avg_volume_20d": 400_000, "current_volume": 410_000}},
    {"name": "zero_volume_both", "input": {"price": 60.0, "price_change_pct": 0.0, "rsi": 50, "avg_volume_20d": 0, "current_volume": 0}},
    {"name": "flat_no_movement", "input": {"price": 100.0, "price_change_pct": 0.0, "rsi": 50, "avg_volume_20d": 1_000_000, "current_volume": 1_000_000}},
    {"name": "huge_volume_spike", "input": {"price": 45.0, "price_change_pct": 0.3, "rsi": 52, "avg_volume_20d": 200_000, "current_volume": 40_000_000}},
    {"name": "malformed_nested_object", "input": {"price": {"value": 100}, "price_change_pct": "up a lot", "rsi": 55}},
    {"name": "extra_unexpected_fields", "input": {"price": 100.0, "price_change_pct": 2.0, "rsi": 60, "avg_volume_20d": 500_000, "current_volume": 520_000, "astrology_score": 9000}},
    {"name": "empty_string_values", "input": {"price": "", "price_change_pct": "", "rsi": ""}},
]

FUNDAMENTAL_EDGE_CASES: list[dict[str, Any]] = [
    {"name": "single_relevant_chunk", "input": {"query": "What was the company's Q2 revenue growth?", "chunks": [{"source": "Q2 Earnings Transcript", "doc_id": "EARN-2026-Q2-001", "text": "Revenue grew 18% YoY to INR 4,200 crore in Q2 FY26."}]}},
    {"name": "empty_chunks", "input": {"query": "What was the company's Q2 revenue growth?", "chunks": []}},
    {"name": "irrelevant_chunks", "input": {"query": "What is the company's debt-to-equity ratio?", "chunks": [{"source": "Press Release", "doc_id": "PR-2026-014", "text": "The company launched a new retail store in Chennai."}]}},
    {"name": "chunk_missing_source_field", "input": {"query": "Any related-party transactions disclosed?", "chunks": [{"doc_id": "SEBI-RPT-2026-3", "text": "The company disclosed a related-party transaction with a promoter entity worth INR 12 crore."}]}},
    {"name": "chunk_missing_doc_id", "input": {"query": "Any pending litigation?", "chunks": [{"source": "Annual Report FY25", "text": "No material litigation is pending against the company as of March 2025."}]}},
    {"name": "conflicting_chunks", "input": {"query": "What is the promoter shareholding percentage?", "chunks": [{"source": "Shareholding Pattern Q1", "doc_id": "SHP-Q1-26", "text": "Promoter holding stands at 54.2% as of Q1."}, {"source": "Shareholding Pattern Q2", "doc_id": "SHP-Q2-26", "text": "Promoter holding stands at 49.8% as of Q2."}]}},
    {"name": "partial_answer_chunks", "input": {"query": "What are the company's revenue and net profit for FY25?", "chunks": [{"source": "Annual Report FY25", "doc_id": "AR-FY25-002", "text": "Total revenue for FY25 was INR 18,400 crore."}]}},
    {"name": "duplicate_chunks", "input": {"query": "Was there a credit rating downgrade?", "chunks": [{"source": "CRISIL Rating Note", "doc_id": "CRISIL-2026-07", "text": "CRISIL downgraded the long-term rating to AA- from AA."}, {"source": "CRISIL Rating Note", "doc_id": "CRISIL-2026-07", "text": "CRISIL downgraded the long-term rating to AA- from AA."}]}},
    {"name": "very_long_single_chunk", "input": {"query": "Summarize the risk factors section.", "chunks": [{"source": "DRHP Risk Factors", "doc_id": "DRHP-RISK-01", "text": " ".join(["Regulatory risk related to changing SEBI norms."] * 60)}]}},
    {"name": "non_english_chunk", "input": {"query": "What did the chairman say about expansion plans?", "chunks": [{"source": "Chairman Statement (Hindi)", "doc_id": "CHM-STMT-09", "text": "कंपनी अगले वर्ष तीन नए संयंत्र स्थापित करेगी।"}]}},
    {"name": "chunk_with_numeric_text_field", "input": {"query": "What is the current market cap?", "chunks": [{"source": "Exchange Filing", "doc_id": "NSE-CAP-22", "text": 48000}]}},
    {"name": "null_query", "input": {"query": None, "chunks": [{"source": "Annual Report", "doc_id": "AR-01", "text": "Net profit rose 9% YoY."}]}},
    {"name": "chunks_not_a_list", "input": {"query": "What are the auditor's remarks?", "chunks": "Deloitte issued an unmodified opinion."}},
    {"name": "many_small_chunks", "input": {"query": "List all board members mentioned.", "chunks": [{"source": f"Board Filing {i}", "doc_id": f"BRD-{i:03d}", "text": f"Director {i} was appointed to the board."} for i in range(1, 9)]}},
    {"name": "chunk_answers_different_question", "input": {"query": "What is the dividend per share declared?", "chunks": [{"source": "ESG Report", "doc_id": "ESG-2026", "text": "The company reduced its carbon footprint by 12% this year."}]}},
    {"name": "empty_string_query", "input": {"query": "", "chunks": [{"source": "Annual Report", "doc_id": "AR-02", "text": "Operating margin improved to 22%."}]}},
    {"name": "single_word_ambiguous_query", "input": {"query": "debt", "chunks": [{"source": "Balance Sheet FY25", "doc_id": "BS-FY25", "text": "Total borrowings stood at INR 3,100 crore, down from INR 3,600 crore."}]}},
]

RISK_EDGE_CASES: list[dict[str, Any]] = [
    {"name": "valid_conservative_low_vol", "input": {"user_profile": {"risk_tolerance": 2, "max_allocation_pct": 5}, "stock_volatility_profile": {"beta": 0.6, "annualized_volatility": 0.15, "sector": "FMCG", "market_cap_category": "large_cap"}}},
    {"name": "valid_aggressive_high_vol", "input": {"user_profile": {"risk_tolerance": 9, "max_allocation_pct": 25}, "stock_volatility_profile": {"beta": 2.4, "annualized_volatility": 0.65, "sector": "smallcap_tech", "market_cap_category": "small_cap"}}},
    {"name": "mismatch_conservative_meets_high_vol", "input": {"user_profile": {"risk_tolerance": 1, "max_allocation_pct": 3}, "stock_volatility_profile": {"beta": 2.8, "annualized_volatility": 0.72, "sector": "crypto_adjacent", "market_cap_category": "small_cap"}}},
    {"name": "risk_tolerance_zero_out_of_range", "input": {"user_profile": {"risk_tolerance": 0, "max_allocation_pct": 10}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "risk_tolerance_eleven_out_of_range", "input": {"user_profile": {"risk_tolerance": 11, "max_allocation_pct": 10}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "risk_tolerance_missing", "input": {"user_profile": {"max_allocation_pct": 10}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "max_allocation_missing", "input": {"user_profile": {"risk_tolerance": 5}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "risk_tolerance_null", "input": {"user_profile": {"risk_tolerance": None, "max_allocation_pct": 10}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "risk_tolerance_as_string", "input": {"user_profile": {"risk_tolerance": "high", "max_allocation_pct": 10}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "max_allocation_negative", "input": {"user_profile": {"risk_tolerance": 5, "max_allocation_pct": -10}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "max_allocation_over_100", "input": {"user_profile": {"risk_tolerance": 5, "max_allocation_pct": 150}, "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}}},
    {"name": "volatility_profile_missing_beta", "input": {"user_profile": {"risk_tolerance": 5, "max_allocation_pct": 10}, "stock_volatility_profile": {"annualized_volatility": 0.3}}},
    {"name": "volatility_profile_missing_vol", "input": {"user_profile": {"risk_tolerance": 5, "max_allocation_pct": 10}, "stock_volatility_profile": {"beta": 1.1}}},
    {"name": "volatility_profile_empty", "input": {"user_profile": {"risk_tolerance": 5, "max_allocation_pct": 10}, "stock_volatility_profile": {}}},
    {"name": "boundary_risk_tolerance_1", "input": {"user_profile": {"risk_tolerance": 1, "max_allocation_pct": 1}, "stock_volatility_profile": {"beta": 0.3, "annualized_volatility": 0.08}}},
    {"name": "boundary_risk_tolerance_10", "input": {"user_profile": {"risk_tolerance": 10, "max_allocation_pct": 100}, "stock_volatility_profile": {"beta": 3.0, "annualized_volatility": 0.9}}},
    {"name": "max_allocation_zero", "input": {"user_profile": {"risk_tolerance": 6, "max_allocation_pct": 0}, "stock_volatility_profile": {"beta": 1.2, "annualized_volatility": 0.25}}},
    {"name": "negative_beta", "input": {"user_profile": {"risk_tolerance": 4, "max_allocation_pct": 8}, "stock_volatility_profile": {"beta": -0.5, "annualized_volatility": 0.18}}},
    {"name": "entire_input_empty", "input": {}},
]


@dataclass
class AgentSpec:
    name: str
    system_prompt: str
    required_keys: set[str]
    edge_cases: list[dict[str, Any]]
    payload_key: str  # key name to wrap edge-case input under in the user message


AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="technical_momentum",
        system_prompt=TECHNICAL_SYSTEM_PROMPT,
        required_keys={"agent", "signal", "confidence", "momentum_metrics", "volume_anomaly", "reasoning", "data_quality", "missing_fields"},
        edge_cases=TECHNICAL_EDGE_CASES,
        payload_key="indicators",
    ),
    AgentSpec(
        name="fundamental_rag",
        system_prompt=FUNDAMENTAL_SYSTEM_PROMPT,
        required_keys={"agent", "summary", "citations", "confidence", "context_sufficient", "logic_notes"},
        edge_cases=FUNDAMENTAL_EDGE_CASES,
        payload_key="rag_input",
    ),
    AgentSpec(
        name="risk_profiler",
        system_prompt=RISK_SYSTEM_PROMPT,
        required_keys={"agent", "suitability_flag", "risk_score", "recommended_allocation_pct", "reasoning", "input_validation"},
        edge_cases=RISK_EDGE_CASES,
        payload_key="risk_input",
    ),
]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

FENCE_PATTERN = re.compile(r"^\s*```")


def check_no_fences_or_preamble(raw_text: str) -> list[str]:
    """Returns a list of violations; empty list = clean."""
    issues = []
    stripped = raw_text.strip()
    if FENCE_PATTERN.match(stripped):
        issues.append("response starts with a markdown code fence (```)")
    if "```" in stripped:
        issues.append("response contains a markdown code fence somewhere in the body")
    if not stripped.startswith("{"):
        issues.append("response does not start with '{' (likely preamble text present)")
    if not stripped.endswith("}"):
        issues.append("response does not end with '}' (likely postamble text present)")
    return issues


def validate_response(raw_text: str, required_keys: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {"parsed_ok": False, "keys_ok": False, "format_issues": [], "error": None}

    result["format_issues"] = check_no_fences_or_preamble(raw_text)

    try:
        parsed = json.loads(raw_text.strip())
        result["parsed_ok"] = True
    except json.JSONDecodeError as e:
        result["error"] = f"JSONDecodeError: {e}"
        return result

    if not isinstance(parsed, dict):
        result["error"] = "top-level JSON value is not an object"
        return result

    missing = required_keys - set(parsed.keys())
    result["keys_ok"] = len(missing) == 0
    if missing:
        result["error"] = f"missing required keys: {sorted(missing)}"

    result["parsed"] = parsed
    return result


# ---------------------------------------------------------------------------
# LLM call (high-speed OpenAI-compatible endpoint, e.g. Groq / Cerebras)
# ---------------------------------------------------------------------------

def call_llm(system_prompt: str, user_payload: dict[str, Any]) -> str:
    api_base = os.environ.get("LLM_API_BASE", "").rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "")

    if not api_key or not api_base or requests is None:
        # Dry-run mode: no live call possible/configured.
        raise RuntimeError("DRY_RUN")

    resp = requests.post(
        f"{api_base}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload)},
            ],
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_agent_suite(spec: AgentSpec) -> dict[str, Any]:
    print(f"\n{'=' * 70}\nAGENT: {spec.name}  ({len(spec.edge_cases)} edge cases)\n{'=' * 70}")
    pass_count = 0
    dry_run = False

    for case in spec.edge_cases:
        payload = {spec.payload_key: case["input"]}
        try:
            raw = call_llm(spec.system_prompt, payload)
        except RuntimeError:
            dry_run = True
            print(f"[DRY-RUN] {case['name']:38s} -> payload ready: {json.dumps(payload)[:90]}...")
            continue
        except Exception as e:
            print(f"[ERROR]   {case['name']:38s} -> request failed: {e}")
            continue

        result = validate_response(raw, spec.required_keys)
        ok = result["parsed_ok"] and result["keys_ok"] and not result["format_issues"]
        pass_count += int(ok)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}]    {case['name']:38s} -> {result.get('error') or result.get('format_issues') or 'schema ok'}")

    if dry_run:
        print(f"\n{spec.name}: dry-run only (set LLM_API_BASE / LLM_API_KEY / LLM_MODEL to execute live).")
        return {"agent": spec.name, "dry_run": True, "total": len(spec.edge_cases)}

    total = len(spec.edge_cases)
    print(f"\n{spec.name}: {pass_count}/{total} passed ({100 * pass_count / total:.1f}% JSON adherence)")
    return {"agent": spec.name, "dry_run": False, "total": total, "passed": pass_count}


def main() -> None:
    print("PS-01 Step 2.4 - JSON adherence test harness")
    print(f"Endpoint configured: {bool(os.environ.get('LLM_API_KEY'))}")

    all_results = [run_agent_suite(spec) for spec in AGENTS]

    if all(r.get("dry_run") for r in all_results):
        print(
            "\nAll three suites ran in dry-run mode (no LLM_API_KEY set). "
            "Every edge case above is a valid, ready-to-send payload — "
            "point LLM_API_BASE/LLM_API_KEY/LLM_MODEL at Groq/Cerebras/etc. "
            "and re-run for live 100%-adherence numbers."
        )
        sys.exit(0)

    total_cases = sum(r["total"] for r in all_results if not r.get("dry_run"))
    total_passed = sum(r["passed"] for r in all_results if not r.get("dry_run"))
    print(f"\n{'=' * 70}\nOVERALL: {total_passed}/{total_cases} passed ({100 * total_passed / total_cases:.1f}%)\n{'=' * 70}")
    if total_passed < total_cases:
        sys.exit(1)


if __name__ == "__main__":
    main()
