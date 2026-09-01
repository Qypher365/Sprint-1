"""
PS-01 Sprint 1 - Technical / Momentum Signal Agent

Implements the "Technical Signal Agent" described in Step 2. Classifies a
stock's momentum signal (BULLISH/BEARISH/NEUTRAL) from a JSON object of
market indicators, flags volume anomalies, and never guesses a missing or
malformed field.

Run standalone:
    python agent_technical.py
"""

from __future__ import annotations

from typing import Any

from agent_base import BaseAgent, is_number

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

EXPECTED_FIELDS = ["price", "price_change_pct", "rsi", "avg_volume_20d", "current_volume"]


class TechnicalMomentumAgent(BaseAgent):
    name = "technical_momentum"
    system_prompt = TECHNICAL_SYSTEM_PROMPT
    payload_key = "indicators"
    required_keys = {
        "agent", "signal", "confidence", "momentum_metrics",
        "volume_anomaly", "reasoning", "data_quality", "missing_fields",
    }

    def run_rule_based(self, data: dict[str, Any]) -> dict[str, Any]:
        data = data or {}

        # Step 1: figure out which expected fields are usably present.
        missing_fields = [f for f in EXPECTED_FIELDS if not is_number(data.get(f))]
        present = {f: data[f] for f in EXPECTED_FIELDS if f not in missing_fields}

        # Step 2: no usable data at all -> NEUTRAL / 0.0 / INSUFFICIENT, per RULES.
        if not present:
            return {
                "agent": self.name,
                "signal": "NEUTRAL",
                "confidence": 0.0,
                "momentum_metrics": {"price_change_pct": None, "rsi": None, "trend": "UNKNOWN"},
                "volume_anomaly": {"detected": False, "ratio_to_avg": None, "description": ""},
                "reasoning": "No usable numeric indicator fields were present in the input.",
                "data_quality": "INSUFFICIENT",
                "missing_fields": EXPECTED_FIELDS,
            }

        price_change_pct = present.get("price_change_pct")
        rsi = present.get("rsi")
        avg_volume_20d = present.get("avg_volume_20d")
        current_volume = present.get("current_volume")

        # Step 3: trend from price_change_pct alone.
        if price_change_pct is None:
            trend = "UNKNOWN"
        elif price_change_pct > 1.0:
            trend = "UP"
        elif price_change_pct < -1.0:
            trend = "DOWN"
        else:
            trend = "SIDEWAYS"

        # Step 4: derive signal, watching for the two indicators disagreeing.
        conflict_note = None
        if price_change_pct is not None and rsi is not None:
            momentum_up = price_change_pct > 2.0
            momentum_down = price_change_pct < -2.0
            if momentum_up and rsi >= 70:
                signal = "NEUTRAL"
                conflict_note = f"price_change_pct={price_change_pct} is strongly positive but rsi={rsi} is overbought (reversal risk) - conflicting signals"
            elif momentum_down and rsi <= 30:
                signal = "NEUTRAL"
                conflict_note = f"price_change_pct={price_change_pct} is strongly negative but rsi={rsi} is oversold (reversal potential) - conflicting signals"
            elif momentum_up:
                signal = "BULLISH"
            elif momentum_down:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"
        elif price_change_pct is not None:
            signal = "BULLISH" if price_change_pct > 2.0 else "BEARISH" if price_change_pct < -2.0 else "NEUTRAL"
        elif rsi is not None:
            signal = "BULLISH" if rsi < 30 else "BEARISH" if rsi > 70 else "NEUTRAL"
        else:
            signal = "NEUTRAL"

        # Step 5: volume anomaly.
        volume_anomaly = {"detected": False, "ratio_to_avg": None, "description": ""}
        if avg_volume_20d is not None and current_volume is not None and avg_volume_20d > 0:
            ratio = round(current_volume / avg_volume_20d, 2)
            detected = ratio >= 1.5 or ratio <= 0.5
            volume_anomaly = {
                "detected": detected,
                "ratio_to_avg": ratio,
                "description": (
                    f"Current volume is {ratio}x the 20-day average" if detected else ""
                ),
            }
        elif avg_volume_20d == 0:
            volume_anomaly["description"] = "avg_volume_20d is zero, cannot compute a ratio"

        # Step 6: confidence + data_quality reflect how much of the schema we actually have.
        completeness = len(present) / len(EXPECTED_FIELDS)
        confidence = round(min(0.95, 0.35 + 0.6 * completeness), 2)
        if conflict_note:
            confidence = round(confidence * 0.5, 2)

        if not missing_fields:
            data_quality = "COMPLETE"
        elif present:
            data_quality = "PARTIAL"
        else:
            data_quality = "INSUFFICIENT"

        reasoning_parts = [f"{k}={v}" for k, v in present.items()]
        reasoning = f"Derived from {', '.join(reasoning_parts)}."
        if conflict_note:
            reasoning += f" {conflict_note}."
        if missing_fields:
            reasoning += f" Missing/invalid: {', '.join(missing_fields)}."

        return {
            "agent": self.name,
            "signal": signal,
            "confidence": confidence,
            "momentum_metrics": {
                "price_change_pct": price_change_pct,
                "rsi": rsi,
                "trend": trend,
            },
            "volume_anomaly": volume_anomaly,
            "reasoning": reasoning,
            "data_quality": data_quality,
            "missing_fields": missing_fields,
        }


if __name__ == "__main__":
    import json as _json

    agent = TechnicalMomentumAgent()
    samples = [
        {"price": 152.4, "price_change_pct": 4.1, "rsi": 68, "avg_volume_20d": 1_200_000, "current_volume": 1_950_000},
        {},
        {"price": 100.0, "price_change_pct": 6.0, "rsi": 89, "avg_volume_20d": 1_000_000, "current_volume": 250_000},
        {"price": 60.0, "price_change_pct": 1.2, "rsi": 51, "avg_volume_20d": "1200000", "current_volume": "1950000"},
    ]
    for s in samples:
        print(f"\ninput: {s}")
        print(_json.dumps(agent.run(s, mode="rule"), indent=2))
