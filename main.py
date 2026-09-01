import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(
    title="Multi-Agent Financial Intelligence API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Request / Response Models
# ============================================================

class AnalyzeRequest(BaseModel):
    ticker: str
    user_profile_id: str
    force_degraded: bool = False


class AnalyzeResponse(BaseModel):
    ticker: str
    user_profile_id: str
    technical: dict[str, Any]
    fundamental: dict[str, Any]
    risk: dict[str, Any]
    synthesis: dict[str, Any]
    degraded_mode: bool
    errors: list[str]


# ============================================================
# Temporary Agent Functions
# These will later be replaced by the actual agent functions
# ============================================================

async def technical_agent(ticker: str) -> dict[str, Any]:
    return {
        "agent": "technical",
        "ticker": ticker,
        "signal": "HOLD",
        "confidence": 0.70,
        "reasoning": ["Technical agent not connected yet."]
    }


async def fundamental_agent(ticker: str) -> dict[str, Any]:
    return {
        "agent": "fundamental",
        "ticker": ticker,
        "signal": "HOLD",
        "confidence": 0.70,
        "reasoning": ["Fundamental agent not connected yet."],
        "citations": []
    }


async def risk_agent(ticker: str, user_profile_id: str) -> dict[str, Any]:
    return {
        "agent": "risk_profiler",
        "ticker": ticker,
        "profile": user_profile_id,
        "risk_level": user_profile_id,
        "confidence": 0.70,
        "reasoning": ["Risk profiler not connected yet."]
    }


# ============================================================
# Safe Agent Runner
# ============================================================

async def run_agent(
    name: str,
    agent_function,
    *args,
    timeout: float = 2.0
) -> tuple[str, dict[str, Any], str | None]:

    try:
        result = await asyncio.wait_for(
            agent_function(*args),
            timeout=timeout
        )

        return name, result, None

    except asyncio.TimeoutError:
        return name, {
            "agent": name,
            "status": "failed",
            "error": "Agent timed out"
        }, f"{name} agent timed out"

    except Exception as exc:
        return name, {
            "agent": name,
            "status": "failed",
            "error": str(exc)
        }, f"{name} agent failed: {exc}"


# ============================================================
# Synthesis
# ============================================================

async def synthesize(results: dict[str, Any]) -> dict[str, Any]:
    """
    Temporary synthesis.
    Sameer's synthesis logic will replace this.
    """

    signals = []

    for agent_name in ["technical", "fundamental"]:
        result = results.get(agent_name, {})
        signal = result.get("signal")

        if signal:
            signals.append(signal)

    if signals.count("BUY") >= 2:
        signal = "BUY"
    elif signals.count("SELL") >= 2:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "signal": signal,
        "confidence_score": 0.70,
        "reasoning_steps": [
            "Collected outputs from specialized agents.",
            "Compared available signals.",
            f"Final signal classified as {signal}."
        ],
        "citations": results.get("fundamental", {}).get("citations", [])
    }


# ============================================================
# Health Check
# ============================================================

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Multi-Agent Financial Intelligence API"
    }


# ============================================================
# Main Analyze Endpoint
# ============================================================

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):

    errors: list[str] = []

    # --------------------------------------------------------
    # Run all 3 agents IN PARALLEL
    # --------------------------------------------------------

    tasks = [
        run_agent(
            "technical",
            technical_agent,
            request.ticker
        ),
        run_agent(
            "fundamental",
            fundamental_agent,
            request.ticker
        ),
        run_agent(
            "risk",
            risk_agent,
            request.ticker,
            request.user_profile_id
        ),
    ]

    results_list = await asyncio.gather(*tasks)

    results = {}

    for name, result, error in results_list:
        results[name] = result

        if error:
            errors.append(error)

    # --------------------------------------------------------
    # Force degraded mode for judging/demo
    # --------------------------------------------------------

    if request.force_degraded:
        errors.append("Degraded mode manually triggered.")

        results["technical"] = {
            "agent": "technical",
            "status": "failed",
            "error": "Simulated network failure"
        }

    degraded_mode = len(errors) > 0

    # --------------------------------------------------------
    # Synthesis
    # --------------------------------------------------------

    synthesis_result = await synthesize(results)

    return AnalyzeResponse(
        ticker=request.ticker,
        user_profile_id=request.user_profile_id,
        technical=results.get("technical", {}),
        fundamental=results.get("fundamental", {}),
        risk=results.get("risk", {}),
        synthesis=synthesis_result,
        degraded_mode=degraded_mode,
        errors=errors
    )