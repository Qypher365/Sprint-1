"""
Runs all three agents (in rule-based / no-network mode) against every edge
case defined in test_json_adherence.py, and validates each output against
that same file's schema + validator — proving 100% structural JSON
adherence offline, and giving a working reference implementation to compare
live LLM outputs against.

    python run_all_agents.py
"""
import json

from agent_base import validate_response
from agent_technical import TechnicalMomentumAgent
from agent_fundamental import FundamentalRagAgent
from agent_risk_profiler import RiskProfilerAgent
from test_json_adherence import TECHNICAL_EDGE_CASES, FUNDAMENTAL_EDGE_CASES, RISK_EDGE_CASES, AGENTS

AGENT_IMPLS = {
    "technical_momentum": (TechnicalMomentumAgent(), TECHNICAL_EDGE_CASES),
    "fundamental_rag": (FundamentalRagAgent(), FUNDAMENTAL_EDGE_CASES),
    "risk_profiler": (RiskProfilerAgent(), RISK_EDGE_CASES),
}
SPECS_BY_NAME = {spec.name: spec for spec in AGENTS}

total_cases = 0
total_passed = 0

for agent_name, (agent, edge_cases) in AGENT_IMPLS.items():
    spec = SPECS_BY_NAME[agent_name]
    print(f"\n{'=' * 70}\nAGENT: {agent_name}  ({len(edge_cases)} edge cases, rule-based mode)\n{'=' * 70}")
    passed = 0
    for case in edge_cases:
        output = agent.run(case["input"], mode="rule")
        raw = json.dumps(output)  # exercises the exact same fence/format checks as a real LLM response would face
        result = validate_response(raw, spec.required_keys)
        ok = result["parsed_ok"] and result["keys_ok"] and not result["format_issues"]
        passed += int(ok)
        total_cases += 1
        total_passed += int(ok)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']:38s} -> {output.get(list(output.keys())[1])}")
    print(f"\n{agent_name}: {passed}/{len(edge_cases)} schema-valid ({100*passed/len(edge_cases):.1f}%)")

print(f"\n{'=' * 70}\nOVERALL: {total_passed}/{total_cases} schema-valid ({100*total_passed/total_cases:.1f}%)\n{'=' * 70}")
