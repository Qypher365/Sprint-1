"""
End-to-end check: runs the three REAL Step-2 agents (rule-based mode, so
fully offline) on a realistic scenario and feeds their actual outputs
straight into SynthesisAgent — proving Step 4 plugs directly into Step 2's
agents with no adapter code needed.

    python integration_check.py
"""
import json

from agent_fundamental import FundamentalRagAgent
from agent_risk_profiler import RiskProfilerAgent
from agent_technical import TechnicalMomentumAgent
from synthesis_agent import SynthesisAgent

technical = TechnicalMomentumAgent()
fundamental = FundamentalRagAgent()
risk = RiskProfilerAgent()
synthesizer = SynthesisAgent()

indicators = {"price": 152.4, "price_change_pct": 4.1, "rsi": 63, "avg_volume_20d": 1_200_000, "current_volume": 2_100_000}
rag_input = {
    "query": "What was the company's Q2 revenue growth?",
    "chunks": [{"source": "Q2 Earnings Transcript", "doc_id": "EARN-2026-Q2-001",
                "text": "Revenue grew 18% YoY to INR 4,200 crore, with strong profit growth in Q2 FY26."}],
}
risk_input = {
    "user_profile": {"risk_tolerance": 6, "max_allocation_pct": 15},
    "stock_volatility_profile": {"beta": 1.3, "annualized_volatility": 0.3},
}

tech_res = technical.run(indicators, mode="rule")
fund_res = fundamental.run(rag_input, mode="rule")
risk_res = risk.run(risk_input, mode="rule")

print("tech_res:", json.dumps(tech_res, indent=2))
print("\nfund_res:", json.dumps(fund_res, indent=2))
print("\nrisk_res:", json.dumps(risk_res, indent=2))

contract = synthesizer.synthesize(tech_res, fund_res, risk_res)
print(f"\n{'=' * 70}\nFINAL SYNTHESIZED CONTRACT\n{'=' * 70}")
print(json.dumps(contract, indent=2))
