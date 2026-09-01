"""
PS-01 Sprint 1 - Agent base class

Shared plumbing for all three specialized agents (technical_momentum,
fundamental_rag, risk_profiler). Each concrete agent below subclasses
`BaseAgent` and supplies:
  - system_prompt   (the exact prompt from Step 2 / test_json_adherence.py)
  - required_keys   (the schema contract from Step 2)
  - payload_key     (the wrapper key used when sending to the LLM)
  - run_rule_based  (a deterministic, pure-Python reference implementation
                      of the SAME task the system prompt describes)

EXECUTION MODES
  agent.run(data, mode="llm")   - calls a real LLM endpoint only. Raises if
                                   the endpoint isn't configured or the
                                   response fails schema validation.
  agent.run(data, mode="rule")  - runs the deterministic Python
                                   implementation only. No network, no LLM.
  agent.run(data, mode="auto")  - [default] tries the LLM first if
                                   LLM_API_BASE/LLM_API_KEY/LLM_MODEL are
                                   set; on any failure (timeout, bad JSON,
                                   missing keys, network error) it falls
                                   back to the rule-based implementation
                                   instead of crashing or returning nothing.
                                   This mirrors the graceful-degradation
                                   contract from Step 3's orchestrator.

Every agent.run() call returns a dict that satisfies the agent's own
required_keys schema, regardless of which path produced it.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:
    import requests
except ImportError:
    requests = None


FENCE_PATTERN = re.compile(r"^\s*```")


def check_no_fences_or_preamble(raw_text: str) -> list[str]:
    """Same format check used in Step 2's test harness."""
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
    """Same validator used in Step 2's test harness — kept in sync deliberately."""
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


def is_number(x: Any) -> bool:
    """True numeric check — excludes bool (isinstance(True, int) is True in Python)."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


class BaseAgent:
    name: str = "base"
    system_prompt: str = ""
    required_keys: set[str] = set()
    payload_key: str = "data"

    def _llm_configured(self) -> bool:
        return bool(
            os.environ.get("LLM_API_BASE")
            and os.environ.get("LLM_API_KEY")
            and os.environ.get("LLM_MODEL")
            and requests is not None
        )

    def call_llm(self, data: dict[str, Any]) -> str:
        """Fires one synchronous call at a high-speed OpenAI-compatible endpoint."""
        if not self._llm_configured():
            raise RuntimeError(
                f"{self.name}: LLM endpoint not configured "
                "(set LLM_API_BASE / LLM_API_KEY / LLM_MODEL)"
            )
        api_base = os.environ["LLM_API_BASE"].rstrip("/")
        api_key = os.environ["LLM_API_KEY"]
        model = os.environ["LLM_MODEL"]

        resp = requests.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps({self.payload_key: data})},
                ],
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def run_rule_based(self, data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(f"{self.name} must implement run_rule_based()")

    def run(self, data: dict[str, Any], mode: str = "auto") -> dict[str, Any]:
        if mode not in ("llm", "rule", "auto"):
            raise ValueError("mode must be 'llm', 'rule', or 'auto'")

        if mode in ("llm", "auto"):
            try:
                raw = self.call_llm(data)
            except Exception as e:
                if mode == "llm":
                    raise
                return self.run_rule_based(data)  # auto: fall back silently, no network available

            validation = validate_response(raw, self.required_keys)
            if validation["parsed_ok"] and validation["keys_ok"] and not validation["format_issues"]:
                return validation["parsed"]
            if mode == "llm":
                raise ValueError(f"{self.name}: LLM output failed schema validation: {validation.get('error')}")
            return self.run_rule_based(data)  # auto: LLM responded but was malformed -> fall back

        return self.run_rule_based(data)  # mode == "rule"
