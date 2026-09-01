import json
from typing import Any

class SynthesisAgent:
    """
    Merges outputs from Technical, Fundamental, and Risk agents into a 
    unified JSON contract: signal, confidence_score, reasoning_steps, citations.
    """
    def synthesize(
        self, 
        tech_res: dict[str, Any], 
        fund_res: dict[str, Any], 
        risk_res: dict[str, Any]
    ) -> dict[str, Any]:
        reasoning_steps = []
        citations = fund_res.get("citations", []) if fund_res else []

        # 1. Evaluate Risk Profile Constraints
        risk_flag = risk_res.get("suitability_flag", "INVALID_INPUT") if risk_res else "INVALID_INPUT"
        risk_reason = risk_res.get("reasoning", "Risk profile unavailable.") if risk_res else "Risk profile unavailable."
        reasoning_steps.append(f"Risk Assessment: Stock is {risk_flag}. {risk_reason}")

        # 2. Evaluate Technical Momentum
        tech_signal = tech_res.get("signal", "NEUTRAL") if tech_res else "NEUTRAL"
        tech_reason = tech_res.get("reasoning", "Technical indicators unavailable.") if tech_res else "Technical indicators unavailable."
        reasoning_steps.append(f"Technical Signal: Classified as {tech_signal}. {tech_reason}")

        # 3. Evaluate Fundamental RAG Context
        fund_summary = fund_res.get("summary", "Fundamental context unavailable.") if fund_res else "Fundamental context unavailable."
        reasoning_steps.append(f"Fundamental Summary: {fund_summary}")

        # 4. Derivation Logic for Unified Signal (BUY / SELL / HOLD)
        if risk_flag in ("UNSUITABLE", "INVALID_INPUT"):
            final_signal = "HOLD"
            reasoning_steps.append("Final Decision: Forced HOLD due to risk profile incompatibility or invalid inputs.")
        elif tech_signal == "BULLISH" and risk_flag in ("SUITABLE", "CAUTION"):
            final_signal = "BUY"
            reasoning_steps.append("Final Decision: BUY based on bullish technical momentum supported by risk tolerance.")
        elif tech_signal == "BEARISH":
            final_signal = "SELL"
            reasoning_steps.append("Final Decision: SELL driven by bearish technical indicators.")
        else:
            final_signal = "HOLD"
            reasoning_steps.append("Final Decision: HOLD due to neutral technical signals or conflicting context.")

        # 5. Compute Weighted Confidence Score
        tech_conf = tech_res.get("confidence", 0.0) if tech_res else 0.0
        fund_conf = fund_res.get("confidence", 0.0) if fund_res else 0.0
        risk_conf = 1.0 if risk_flag in ("SUITABLE", "CAUTION") else 0.2 if risk_flag == "UNSUITABLE" else 0.0

        confidence_score = round((tech_conf * 0.4) + (fund_conf * 0.4) + (risk_conf * 0.2), 2)

        return {
            "signal": final_signal,
            "confidence_score": confidence_score,
            "reasoning_steps": reasoning_steps,
            "citations": citations
        }