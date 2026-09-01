"""
PS-01 Sprint 1 - Step 3: Asynchronous Agent Orchestration

Fires the three specialized agents (technical_momentum, fundamental_rag,
risk_profiler) SIMULTANEOUSLY via asyncio, then synthesizes their structured
outputs into one user-facing response.

Directly implements the PS-01 minimum requirements:
  - "at least three specialized agents execute in parallel ... consumed by
    a synthesis layer"
  - "graceful handling of at least one degraded-data scenario ... without
    the pipeline failing or producing an uncited output"
  - "a performance log capturing at least three measurable metrics per
    session"
  - "a logging and persistence mechanism to store agent outputs ... across
    sessions"

Builds on the system prompts and schemas defined in Step 2
(agent_system_prompts.md / test_json_adherence.py) — this module imports
the prompts and required-key schemas from test_json_adherence.py directly,
so both steps stay in sync.

HOW TO RUN
    python orchestrator.py

    - With no LLM_API_KEY set, runs a self-contained MOCK demo: one full
      "all agents healthy" pass, one "agent timeout" degraded pass, and one
      "agent returns malformed JSON" degraded pass — proving true
      concurrency and graceful degradation without hitting a real network.
    - With LLM_API_BASE / LLM_API_KEY / LLM_MODEL set (same env vars as
      Step 2), it fires real concurrent calls at a high-speed
      OpenAI-compatible endpoint (Groq / Cerebras / Together / etc.).
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from reliance_feed import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from test_json_adherence import (
    AGENTS,
    AgentSpec,
    FUNDAMENTAL_SYSTEM_PROMPT,
    RISK_SYSTEM_PROMPT,
    TECHNICAL_SYSTEM_PROMPT,
    validate_response,
)
from perf_config import (
    AGENT_TIMEOUT_S,
    OPTIMIZED_AGENTS,
    PIPELINE_TARGET_S,
    resolve_provider_env,
    select_top_chunks,
)

LOG_PATH = Path(__file__).parent / "session_log.jsonl"
# Step 5.4: per-agent asyncio.wait_for() guard, tightened from the original
# 12.0s (safe-but-slow default from Step 3) to 1.5s so the Synthesis agent
# always gets control before the 2.0s pipeline target is breached.
DEFAULT_TIMEOUT_S = AGENT_TIMEOUT_S


# ---------------------------------------------------------------------------
# Status model
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"          # valid JSON, all required keys present
    MALFORMED = "MALFORMED"      # response returned but failed JSON/schema validation
    TIMEOUT = "TIMEOUT"          # agent did not respond within the deadline
    ERROR = "ERROR"              # transport-level exception (network, auth, etc.)


@dataclass
class AgentResult:
    agent_name: str
    status: AgentStatus
    latency_ms: float
    parsed: Optional[dict[str, Any]] = None
    raw_response: Optional[str] = None
    error: Optional[str] = None

    def to_log_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
        }


@dataclass
class PipelineResult:
    session_id: str
    started_at: float
    total_latency_ms: float
    agent_results: list[AgentResult]
    synthesis: dict[str, Any]
    synthesis_latency_ms: float = 0.0  # Step 5.1: Tsynth

    def metrics(self) -> dict[str, Any]:
        """At least three measurable metrics per session, per PS-01 requirement."""
        degraded = [r for r in self.agent_results if r.status != AgentStatus.SUCCESS]
        return {
            "pipeline_total_latency_ms": round(self.total_latency_ms, 1),
            "per_agent_latency_ms": {r.agent_name: round(r.latency_ms, 1) for r in self.agent_results},
            "synthesis_latency_ms": round(self.synthesis_latency_ms, 2),
            "agents_degraded_count": len(degraded),
            "agents_degraded": [r.agent_name for r in degraded],
            "under_2s_target": self.total_latency_ms < PIPELINE_TARGET_S * 1000,
        }


# ---------------------------------------------------------------------------
# Transport layer — pluggable so the same orchestrator runs against a mock
# (for local/offline testing) or a real high-speed LLM endpoint.
# ---------------------------------------------------------------------------

Transport = Callable[[str, dict[str, Any]], Awaitable[str]]


async def real_llm_transport(system_prompt: str, user_payload: dict[str, Any]) -> str:
    """Calls a real OpenAI-compatible chat completions endpoint asynchronously."""
    import aiohttp  # imported lazily so the mock demo has zero extra deps

    api_base = os.environ["LLM_API_BASE"].rstrip("/")
    api_key = os.environ["LLM_API_KEY"]
    model = os.environ["LLM_MODEL"]

    async with aiohttp.ClientSession() as session:
        async with session.post(
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
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["choices"][0]["message"]["content"]


def make_real_transport_for(agent_name: str) -> Transport:
    """
    Step 5.3: builds a real transport bound to ONE agent's resolved
    provider env vars (TECH_LLM_*/RISK_LLM_*/FUND_LLM_*, falling back to
    the generic LLM_API_*). This is what lets technical_momentum and
    risk_profiler be pointed at a low-latency provider (Groq, Cerebras,
    Together running Llama-3-8B / Qwen2.5) while fundamental_rag stays on
    a stronger default model for citation-quality RAG reasoning.
    """

    async def _transport(system_prompt: str, user_payload: dict[str, Any]) -> str:
        import aiohttp  # imported lazily so the mock demo has zero extra deps

        env = resolve_provider_env(agent_name)
        api_base = env["LLM_API_BASE"].rstrip("/")
        api_key = env["LLM_API_KEY"]
        model = env["LLM_MODEL"]

        async with aiohttp.ClientSession() as session:
            async with session.post(
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
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    return _transport


def make_dispatching_transport(transports_by_agent: dict[str, Transport]) -> Transport:
    """
    Wraps per-agent transports into the single `Transport` shape
    AgentOrchestrator expects, dispatching on which system prompt is being
    sent (same detection AgentOrchestrator's mock transport already uses).
    """

    async def _transport(system_prompt: str, user_payload: dict[str, Any]) -> str:
        if "Technical Signal Agent" in system_prompt:
            agent_name = "technical_momentum"
        elif "Fundamental Research Agent" in system_prompt:
            agent_name = "fundamental_rag"
        else:
            agent_name = "risk_profiler"
        return await transports_by_agent[agent_name](system_prompt, user_payload)

    return _transport


def make_mock_transport(behavior: dict[str, str]) -> Transport:
    """
    Builds a mock transport for offline testing / demoing degraded scenarios.
    `behavior` maps agent_name -> "ok" | "timeout" | "malformed" | "error".
    """

    async def _transport(system_prompt: str, user_payload: dict[str, Any]) -> str:
        # Identify which agent this is from the system prompt content.
        if "Technical Signal Agent" in system_prompt:
            agent_name, mode = "technical_momentum", behavior.get("technical_momentum", "ok")
        elif "Fundamental Research Agent" in system_prompt:
            agent_name, mode = "fundamental_rag", behavior.get("fundamental_rag", "ok")
        else:
            agent_name, mode = "risk_profiler", behavior.get("risk_profiler", "ok")

        # Simulate realistic network latency for a high-speed inference endpoint.
        await asyncio.sleep(0.4)

        if mode == "timeout":
            await asyncio.sleep(30)  # will be cut off by asyncio.wait_for upstream
            return "{}"
        if mode == "error":
            raise ConnectionError(f"simulated transport failure for {agent_name}")
        if mode == "malformed":
            return "Sure! Here is the analysis:\n```json\n{\"agent\": \"" + agent_name + "\"}\n```"

        # "ok" — return a schema-valid mock response per agent.
        if agent_name == "technical_momentum":
            return json.dumps({
                "agent": "technical_momentum", "signal": "BULLISH", "confidence": 0.74,
                "momentum_metrics": {"price_change_pct": 3.2, "rsi": 63, "trend": "UP"},
                "volume_anomaly": {"detected": True, "ratio_to_avg": 1.8, "description": "Volume 1.8x 20d average"},
                "reasoning": "rsi=63 and price_change_pct=3.2 with volume 1.8x avg support BULLISH",
                "data_quality": "COMPLETE", "missing_fields": [],
            })
        if agent_name == "fundamental_rag":
            return json.dumps({
                "agent": "fundamental_rag",
                "summary": "Q2 revenue grew 18% YoY to INR 4,200 crore per the earnings transcript.",
                "citations": [{"source": "Q2 Earnings Transcript", "doc_id": "EARN-2026-Q2-001", "excerpt_ref": "revenue grew 18% YoY"}],
                "confidence": 0.81, "context_sufficient": True, "logic_notes": "",
            })
        return json.dumps({
            "agent": "risk_profiler", "suitability_flag": "CAUTION", "risk_score": 62.0,
            "recommended_allocation_pct": 4.0,
            "reasoning": "risk_tolerance=4 vs beta=1.9 drives CAUTION, allocation capped at user's 5% max",
            "input_validation": {"valid": True, "issues": []},
        })

    return _transport


# ---------------------------------------------------------------------------
# Persistence — session log (append-only JSONL), the "logging and
# persistence mechanism" dependency from the PS.
# ---------------------------------------------------------------------------

def persist_session(result: PipelineResult) -> None:
    record = {
        "session_id": result.session_id,
        "started_at": result.started_at,
        "metrics": result.metrics(),
        "agent_results": [r.to_log_dict() for r in result.agent_results],
        "synthesis_data_quality": result.synthesis["overall_data_quality"],
    }
    with LOG_PATH.open("a") as f:
        f.write(json.dumps(record) + "\n")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class AgentOrchestrator:
    def __init__(
        self,
        transport: Transport,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        agent_specs: list[AgentSpec] | None = None,
    ):
        self.transport = transport
        self.timeout_s = timeout_s
        # Step 5.2: pass agent_specs=OPTIMIZED_AGENTS to run on the pruned
        # system prompts. Defaults to the original Step 2 AGENTS so nothing
        # that already calls AgentOrchestrator(...) without this arg changes
        # behavior.
        specs = agent_specs if agent_specs is not None else AGENTS
        self.specs_by_name: dict[str, AgentSpec] = {spec.name: spec for spec in specs}

    async def _call_single_agent(self, spec: AgentSpec, payload: dict[str, Any]) -> AgentResult:
        """
        Calls one agent with a hard timeout and full exception isolation.
        A failure here NEVER raises — it always degrades to a flagged
        AgentResult so asyncio.gather never has to abort sibling tasks.
        """
        start = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                self.transport(spec.system_prompt, {spec.payload_key: payload}),
                timeout=self.timeout_s,
            )
        except asyncio.TimeoutError:
            return AgentResult(
                agent_name=spec.name, status=AgentStatus.TIMEOUT,
                latency_ms=(time.monotonic() - start) * 1000,
                error=f"no response within {self.timeout_s}s",
            )
        except Exception as e:  # transport-level failure (network, auth, etc.)
            return AgentResult(
                agent_name=spec.name, status=AgentStatus.ERROR,
                latency_ms=(time.monotonic() - start) * 1000,
                error=f"{type(e).__name__}: {e}",
            )

        latency_ms = (time.monotonic() - start) * 1000
        validation = validate_response(raw, spec.required_keys)
        if validation["parsed_ok"] and validation["keys_ok"] and not validation["format_issues"]:
            return AgentResult(
                agent_name=spec.name, status=AgentStatus.SUCCESS,
                latency_ms=latency_ms, parsed=validation["parsed"], raw_response=raw,
            )
        return AgentResult(
            agent_name=spec.name, status=AgentStatus.MALFORMED,
            latency_ms=latency_ms, raw_response=raw,
            error=validation.get("error") or "; ".join(validation["format_issues"]),
        )

    async def run(
        self,
        technical_indicators: dict[str, Any],
        rag_input: dict[str, Any],
        risk_input: dict[str, Any],
    ) -> PipelineResult:
        session_id = str(uuid.uuid4())
        started_at = time.time()
        pipeline_start = time.monotonic()

        # Step 5.2: cap the RAG context BEFORE it's sent anywhere - top 3
        # chunks, ~800 tokens total - rather than trusting the caller to
        # have already trimmed it.
        rag_input = {
            **rag_input,
            "chunks": select_top_chunks(rag_input.get("query", ""), rag_input.get("chunks", [])),
        }

        # Fire all three agents SIMULTANEOUSLY. return_exceptions=True is a
        # second safety net on top of the try/except inside
        # _call_single_agent, so one agent crashing can never take down the
        # other two in-flight calls or the pipeline as a whole.
        payloads = {
            "technical_momentum": technical_indicators,
            "fundamental_rag": rag_input,
            "risk_profiler": risk_input,
        }
        tasks = [
            self._call_single_agent(self.specs_by_name[name], payloads[name])
            for name in payloads
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        agent_results: list[AgentResult] = []
        for name, r in zip(payloads.keys(), raw_results):
            if isinstance(r, Exception):
                agent_results.append(AgentResult(
                    agent_name=name, status=AgentStatus.ERROR,
                    latency_ms=0.0, error=f"unhandled {type(r).__name__}: {r}",
                ))
            else:
                agent_results.append(r)

        # Step 5.1: instrument synthesis latency (Tsynth) separately from
        # per-agent latency so the benchmark can show it's negligible next
        # to network/LLM time - synthesize() is pure Python, no I/O.
        synth_start = time.monotonic()
        synthesis = synthesize(agent_results)
        synthesis_latency_ms = (time.monotonic() - synth_start) * 1000

        total_latency_ms = (time.monotonic() - pipeline_start) * 1000

        result = PipelineResult(
            session_id=session_id, started_at=started_at,
            total_latency_ms=total_latency_ms, agent_results=agent_results,
            synthesis=synthesis, synthesis_latency_ms=synthesis_latency_ms,
        )
        persist_session(result)
        return result


# ---------------------------------------------------------------------------
# Synthesis layer
# ---------------------------------------------------------------------------

def synthesize(agent_results: list[AgentResult]) -> dict[str, Any]:
    """
    Combines the three agent outputs into one user-facing object.

    Hard rule (matches the PS-01 requirement to never produce an uncited
    output on degraded data): if an agent failed/timed out/returned
    malformed JSON, its section is explicitly marked unavailable — never
    silently dropped, and never backfilled with a guess.
    """
    by_name = {r.agent_name: r for r in agent_results}
    sections: dict[str, Any] = {}
    degraded_agents: list[str] = []

    for name, result in by_name.items():
        if result.status == AgentStatus.SUCCESS:
            sections[name] = {"available": True, "data": result.parsed}
        else:
            degraded_agents.append(name)
            sections[name] = {
                "available": False,
                "reason": f"{result.status.value}: {result.error}",
                "data": None,
            }

    if not degraded_agents:
        overall = "COMPLETE"
    elif len(degraded_agents) < len(by_name):
        overall = "DEGRADED"
    else:
        overall = "FAILED"

    # Build a plain-language, fully-attributed recommendation string using
    # ONLY the sections that actually came back — this is the mechanism
    # that satisfies "graceful handling ... without producing an uncited
    # output."
    lines = []
    tech = sections.get("technical_momentum", {})
    fund = sections.get("fundamental_rag", {})
    risk = sections.get("risk_profiler", {})

    if tech.get("available"):
        d = tech["data"]
        lines.append(f"Technical signal: {d['signal']} (confidence {d['confidence']}) — {d['reasoning']}")
    else:
        lines.append(f"Technical signal: UNAVAILABLE this session ({tech.get('reason')}).")

    if fund.get("available"):
        d = fund["data"]
        cite_str = "; ".join(f"{c['source']} ({c['doc_id']})" for c in d["citations"]) or "no supporting source found"
        lines.append(f"Fundamentals: {d['summary']} [Sources: {cite_str}]")
    else:
        lines.append(f"Fundamentals: UNAVAILABLE this session ({fund.get('reason')}).")

    if risk.get("available"):
        d = risk["data"]
        lines.append(f"Suitability for this user: {d['suitability_flag']} — {d['reasoning']}")
    else:
        lines.append(f"Suitability check: UNAVAILABLE this session ({risk.get('reason')}).")

    if degraded_agents:
        lines.append(
            f"Note: {', '.join(degraded_agents)} did not return a usable result this session; "
            "the recommendation above reflects only the agents that succeeded."
        )

    return {
        "overall_data_quality": overall,
        "degraded_agents": degraded_agents,
        "sections": sections,
        "narrative": "\n".join(lines),
    }


# ---------------------------------------------------------------------------
# Demo / self-test
# ---------------------------------------------------------------------------

SAMPLE_TECHNICAL_INPUT = {
    "price": 152.4, "price_change_pct": 3.2, "rsi": 63,
    "avg_volume_20d": 1_200_000, "current_volume": 2_150_000,
}
SAMPLE_RAG_INPUT = {
    "query": "What was the company's Q2 revenue growth?",
    "chunks": [{"source": "Q2 Earnings Transcript", "doc_id": "EARN-2026-Q2-001",
                "text": "Revenue grew 18% YoY to INR 4,200 crore in Q2 FY26."}],
}
SAMPLE_RISK_INPUT = {
    "user_profile": {"risk_tolerance": 4, "max_allocation_pct": 5},
    "stock_volatility_profile": {"beta": 1.9, "annualized_volatility": 0.42, "sector": "midcap_industrials"},
}


async def demo_scenario(label: str, transport: Transport) -> None:
    print(f"\n{'=' * 70}\nSCENARIO: {label}\n{'=' * 70}")
    orchestrator = AgentOrchestrator(transport=transport, timeout_s=AGENT_TIMEOUT_S)
    t0 = time.monotonic()
    result = await orchestrator.run(SAMPLE_TECHNICAL_INPUT, SAMPLE_RAG_INPUT, SAMPLE_RISK_INPUT)
    wall_clock_ms = (time.monotonic() - t0) * 1000

    print(f"session_id: {result.session_id}")
    print(f"wall-clock pipeline time: {wall_clock_ms:.0f}ms  (proves parallel execution, not sum of agent latencies)")
    print(f"metrics: {json.dumps(result.metrics(), indent=2)}")
    print(f"overall_data_quality: {result.synthesis['overall_data_quality']}")
    print("---\nNARRATIVE (final synthesized, user-facing output):")
    print(result.synthesis["narrative"])


async def main() -> None:
    use_real = bool(os.environ.get("LLM_API_KEY"))

    if use_real:
        print(
            "LLM_API_KEY detected — running ONE real pipeline pass with Step 5 optimizations: "
            "pruned prompts, top-3/800-token RAG context, per-agent fast-provider routing, "
            f"{AGENT_TIMEOUT_S}s per-agent timeout guard."
        )
        transport = make_dispatching_transport({
            "technical_momentum": make_real_transport_for("technical_momentum"),
            "fundamental_rag": make_real_transport_for("fundamental_rag"),
            "risk_profiler": make_real_transport_for("risk_profiler"),
        })
        orchestrator = AgentOrchestrator(transport=transport, agent_specs=OPTIMIZED_AGENTS)
        result = await orchestrator.run(SAMPLE_TECHNICAL_INPUT, SAMPLE_RAG_INPUT, SAMPLE_RISK_INPUT)
        print(json.dumps(result.metrics(), indent=2))
        print(result.synthesis["narrative"])
        return

    print(
        "No LLM_API_KEY set — running offline MOCK demo of three scenarios "
        "to prove (a) true concurrency and (b) graceful degraded-data handling.\n"
        "(Set LLM_API_BASE / LLM_API_KEY / LLM_MODEL to run against a real endpoint instead.)"
    )

    await demo_scenario(
        "All three agents healthy",
        make_mock_transport({"technical_momentum": "ok", "fundamental_rag": "ok", "risk_profiler": "ok"}),
    )
    await demo_scenario(
        "Degraded: risk_profiler times out (unavailable data feed analog)",
        make_mock_transport({"technical_momentum": "ok", "fundamental_rag": "ok", "risk_profiler": "timeout"}),
    )
    await demo_scenario(
        "Degraded: fundamental_rag returns malformed/fenced JSON (missing filing analog)",
        make_mock_transport({"technical_momentum": "ok", "fundamental_rag": "malformed", "risk_profiler": "ok"}),
    )
    await demo_scenario(
        "Degraded: technical_momentum transport error (data feed unavailable)",
        make_mock_transport({"technical_momentum": "error", "fundamental_rag": "ok", "risk_profiler": "ok"}),
    )

    print(f"\nSession log persisted to: {LOG_PATH}")


def _run_async(coro):
    """
    Runs a coroutine from the top level, working both in a plain terminal
    (python orchestrator.py) and in a console that already has its own
    event loop running — e.g. Spyder's IPython console or a Jupyter
    notebook, where a bare asyncio.run() raises:
        RuntimeError: asyncio.run() cannot be called from a running event loop

    No extra dependency required: when a loop is already running, this
    spins the coroutine up on a brand-new event loop in a separate thread
    and blocks until it's done, instead of trying to reuse/patch the
    console's own loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop is running yet (plain terminal / plain `python file.py`) — normal path.
        return asyncio.run(coro)

    import threading

    result_box: dict[str, Any] = {}

    def _worker():
        result_box["result"] = asyncio.run(coro)

    thread = threading.Thread(target=_worker)
    thread.start()
    thread.join()
    return result_box["result"]


if __name__ == "__main__":
    _run_async(main())
