"""
PS-01 Sprint 1 - Risk Profiler / Suitability Agent

Implements the "Risk Profiler Agent" described in Step 2. Validates a
user's risk_tolerance (1-10) and max_allocation_pct against a stock's
volatility profile, and produces a suitability_flag + capped allocation
recommendation — or INVALID_INPUT if the inputs don't pass validation.

Run standalone:
    python agent_risk_profiler.py
"""

from __future__ import annotations

from typing import Any

from agent_base import BaseAgent, is_number

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


class RiskProfilerAgent(BaseAgent):
    name = "risk_profiler"
    system_prompt = RISK_SYSTEM_PROMPT
    payload_key = "risk_input"
    required_keys = {
        "agent", "suitability_flag", "risk_score", "recommended_allocation_pct",
        "reasoning", "input_validation",
    }

    def _invalid(self, issues: list[str]) -> dict[str, Any]:
        return {
            "agent": self.name,
            "suitability_flag": "INVALID_INPUT",
            "risk_score": None,
            "recommended_allocation_pct": None,
            "reasoning": "Input validation failed before any suitability judgement was attempted.",
            "input_validation": {"valid": False, "issues": issues},
        }

    def run_rule_based(self, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}
        user_profile = data.get("user_profile") if isinstance(data.get("user_profile"), dict) else {}
        volatility = data.get("stock_volatility_profile") if isinstance(data.get("stock_volatility_profile"), dict) else {}

        issues: list[str] = []

        risk_tolerance = user_profile.get("risk_tolerance")
        if not isinstance(risk_tolerance, int) or isinstance(risk_tolerance, bool):
            issues.append("risk_tolerance is missing or not an integer")
        elif not (1 <= risk_tolerance <= 10):
            issues.append(f"risk_tolerance={risk_tolerance} is out of the required 1-10 range")

        max_allocation_pct = user_profile.get("max_allocation_pct")
        if not is_number(max_allocation_pct):
            issues.append("max_allocation_pct is missing or not a number")
        elif not (0 <= max_allocation_pct <= 100):
            issues.append(f"max_allocation_pct={max_allocation_pct} is out of the required 0-100 range")

        beta = volatility.get("beta")
        if not is_number(beta):
            issues.append("stock_volatility_profile.beta is missing or not a number")

        annualized_volatility = volatility.get("annualized_volatility")
        if not is_number(annualized_volatility):
            issues.append("stock_volatility_profile.annualized_volatility is missing or not a number")

        if issues:
            return self._invalid(issues)

        # All inputs validated — compute risk_score (0-100, higher = riskier
        # stock relative to typical ranges) using |beta| and volatility.
        risk_score = round(min(100.0, max(0.0, (abs(beta) / 3.0) * 50 + min(annualized_volatility, 1.0) * 50)), 1)

        # User's risk capacity, scaled to the same 0-100 axis.
        capacity_score = risk_tolerance * 10

        if risk_score <= capacity_score - 15:
            suitability_flag = "SUITABLE"
            allocation_factor = 1.0
        elif risk_score <= capacity_score + 15:
            suitability_flag = "CAUTION"
            allocation_factor = 0.5
        else:
            suitability_flag = "UNSUITABLE"
            allocation_factor = 0.15

        recommended_allocation_pct = round(min(max_allocation_pct, max_allocation_pct * allocation_factor), 2)

        reasoning = (
            f"risk_tolerance={risk_tolerance} (capacity_score={capacity_score}) vs "
            f"beta={beta}, annualized_volatility={annualized_volatility} (risk_score={risk_score}) "
            f"drives {suitability_flag}; allocation capped at user's max_allocation_pct={max_allocation_pct}."
        )

        return {
            "agent": self.name,
            "suitability_flag": suitability_flag,
            "risk_score": risk_score,
            "recommended_allocation_pct": recommended_allocation_pct,
            "reasoning": reasoning,
            "input_validation": {"valid": True, "issues": []},
        }


if __name__ == "__main__":
    import json as _json

    agent = RiskProfilerAgent()
    samples = [
        {"user_profile": {"risk_tolerance": 2, "max_allocation_pct": 5},
         "stock_volatility_profile": {"beta": 0.6, "annualized_volatility": 0.15}},
        {"user_profile": {"risk_tolerance": 9, "max_allocation_pct": 25},
         "stock_volatility_profile": {"beta": 2.4, "annualized_volatility": 0.65}},
        {"user_profile": {"risk_tolerance": 0, "max_allocation_pct": 10},
         "stock_volatility_profile": {"beta": 1.0, "annualized_volatility": 0.2}},
        {"user_profile": {"risk_tolerance": 5, "max_allocation_pct": 10},
         "stock_volatility_profile": {}},
        {},
    ]
    for s in samples:
        print(f"\ninput: {s}")
        print(_json.dumps(agent.run(s, mode="rule"), indent=2))
