"""
DataShield - FastAPI Backend / Multi-Agent Orchestrator

This file is the integration layer between:
- Divyansh's mock market feeds
- Shlok's Supabase user_profiles + pgvector RAG
- Sameer's Technical, Fundamental and Synthesis agents
- Swastik's Next.js frontend

Required local files:
    main.py
    agent_base.py
    technical.py
    fundamental.py
    synthesis.py

Optional:
    risk_profiler.py  (the original Sameer risk profiler is NOT called directly
                       because the live DB does not contain its required numeric
                       risk_tolerance/max_allocation/beta/volatility fields.)

Environment:
    SUPABASE_URL
    SUPABASE_KEY
    GEMINI_API_KEY

Optional LLM variables used by Sameer's BaseAgent:
    LLM_API_BASE
    LLM_API_KEY
    LLM_MODEL
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from supabase import Client, create_client

from agents.technical import TechnicalMomentumAgent
from agents.fundamental import FundamentalRagAgent
from agents.synthesis import SynthesisAgent


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://vahhwrwezfwumbajxqzg.supabase.co",
).strip().rstrip("/")

SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_KEY is missing from .env")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing from .env")

if "/rest/v1" in SUPABASE_URL.lower():
    raise RuntimeError(
        "SUPABASE_URL must contain only the Supabase project URL, "
        "not /rest/v1."
    )


# ============================================================
# CLIENTS
# ============================================================

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)

gemini = genai.Client(
    api_key=GEMINI_API_KEY,
)


# ============================================================
# APP
# ============================================================

app = FastAPI(
    title="DataShield API",
    description="AI Financial Advisory Guardrail Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# CONFIG
# ============================================================

AGENT_TIMEOUT = 12.0
DATA_DIRECTORY = Path(__file__).resolve().parent / "data"

TECHNICAL_AGENT = TechnicalMomentumAgent()
FUNDAMENTAL_AGENT = FundamentalRagAgent()
SYNTHESIS_AGENT = SynthesisAgent()


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class QueryRequest(BaseModel):
    user_id: str
    query: str
    ticker: str | None = None
    force_degraded: bool = False


class AnalyzeRequest(BaseModel):
    ticker: str
    user_profile_id: str
    force_degraded: bool = False
    query: str | None = None


class QueryResponse(BaseModel):
    answer: str
    risk_flag: bool
    user_risk_category: str
    sources: list[str]

    technical: dict[str, Any]
    fundamental: dict[str, Any]
    risk: dict[str, Any]
    synthesis: dict[str, Any]

    degraded_mode: bool
    errors: list[str]


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
# USER PROFILE
# ============================================================

def get_user_profile(user_id: str) -> dict[str, Any]:
    """
    Actual live schema:

        public.user_profiles
            id                TEXT PRIMARY KEY
            risk_tolerance    TEXT
            portfolio_value   NUMERIC
            preferred_sectors TEXT[]

    Current profiles:
        user_retail_safe -> conservative
        user_fno_degen   -> aggressive
    """

    try:
        response = (
            supabase
            .table("user_profiles")
            .select(
                "id, risk_tolerance, "
                "portfolio_value, preferred_sectors"
            )
            .eq("id", user_id)
            .single()
            .execute()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch user profile: {exc}",
        )

    if not response.data:
        raise HTTPException(
            status_code=404,
            detail=f"User profile not found: {user_id}",
        )

    return response.data


# ============================================================
# GEMINI EMBEDDING
# ============================================================

def generate_query_embedding(query: str) -> list[float]:
    try:
        response = gemini.models.embed_content(
            model="gemini-embedding-001",
            contents=query,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
    except Exception as exc:
        raise RuntimeError(
            f"Embedding generation failed: {exc}"
        )

    if not response.embeddings:
        raise RuntimeError(
            "Gemini returned no embedding."
        )

    vector = response.embeddings[0].values

    if len(vector) != 768:
        raise RuntimeError(
            f"Expected 768-dimensional embedding, got {len(vector)}."
        )

    return vector


# ============================================================
# SUPABASE RAG
# ============================================================

def search_documents(
    query_vector: list[float],
) -> list[dict[str, Any]]:
    """
    IMPORTANT:
    Shlok confirmed the RPC is match_documents (singular).
    """

    try:
        response = supabase.rpc(
            "match_documents",
            {
                "query_embedding": query_vector,
                "match_threshold": 0.1,
                "match_count": 3,
            },
        ).execute()
    except Exception as exc:
        raise RuntimeError(
            f"Vector search failed: {exc}"
        )

    return response.data or []


def convert_rag_chunks(
    documents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Converts Shlok's RPC schema:

        id, source_name, content, similarity

    into Sameer's Fundamental Agent schema:

        source, doc_id, text
    """

    chunks: list[dict[str, Any]] = []

    for document in documents:
        source = document.get("source_name")
        doc_id = document.get("id")
        content = document.get("content")

        if not source or not doc_id or not content:
            continue

        chunks.append(
            {
                "source": str(source),
                "doc_id": str(doc_id),
                "text": str(content),
            }
        )

    return chunks


# ============================================================
# MARKET FEEDS
# ============================================================

def load_market_feed(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper().strip()

    filename_map = {
        "TATAMOTORS": "tata_motors_feed.json",
        "RELIANCE": "reliance_feed.json",
        "INFY": "infosys_feed.json",
        "INFOSYS": "infosys_feed.json",
    }

    filename = filename_map.get(ticker)

    if not filename:
        raise ValueError(
            f"Unsupported ticker: {ticker}. "
            "Supported: TATAMOTORS, RELIANCE, INFY."
        )

    path = DATA_DIRECTORY / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Market feed not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {filename}: {exc}"
        )


# ============================================================
# TECHNICAL ADAPTER
# ============================================================

def build_technical_input(
    market_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Divyansh's feed -> Sameer's Technical Agent contract.

    Sameer's agent expects:
        price
        price_change_pct
        rsi
        avg_volume_20d
        current_volume

    The feed provides:
        price_data.last_traded_price
        price_data.day_change_pct
        signals.volume_anomaly.avg_volume_30d
        signals.volume_anomaly.current_volume

    RSI is NOT fabricated. It remains absent unless the feed
    explicitly provides a numeric RSI.
    """

    price_data = market_data.get("price_data") or {}
    signals = market_data.get("signals") or {}
    volume = signals.get("volume_anomaly") or {}

    indicators: dict[str, Any] = {
        "price": price_data.get("last_traded_price"),
        "price_change_pct": price_data.get("day_change_pct"),
        "rsi": None,
        "avg_volume_20d": volume.get("avg_volume_30d"),
        "current_volume": volume.get("current_volume"),
    }

    # If a future feed contains a numeric RSI, use it.
    possible_rsi = (
        signals.get("price_momentum", {}).get("rsi")
        if isinstance(signals.get("price_momentum"), dict)
        else None
    )

    if isinstance(possible_rsi, (int, float)) and not isinstance(
        possible_rsi, bool
    ):
        indicators["rsi"] = possible_rsi

    return indicators


# ============================================================
# RISK ADAPTER
# ============================================================

def build_risk_result(
    profile: dict[str, Any],
    market_data: dict[str, Any],
    ticker: str,
) -> dict[str, Any]:
    """
    Sameer's RiskProfilerAgent requires:
        numeric risk_tolerance 1-10
        max_allocation_pct
        beta
        annualized_volatility

    The LIVE DB only has:
        conservative/aggressive
        portfolio_value
        preferred_sectors

    Therefore we do NOT invent beta/annualized volatility just to
    satisfy that agent. Instead this deterministic adapter maps
    the actual stored profile into Sameer's OUTPUT CONTRACT.

    Profile mapping:
        conservative -> risk capacity 2/10, max allocation 5%
        aggressive   -> risk capacity 9/10, max allocation 25%

    The stock feed's own anomaly/sentiment information is used as
    risk evidence, without pretending it is beta or annualized
    volatility.
    """

    tolerance = str(
        profile.get("risk_tolerance", "")
    ).lower().strip()

    portfolio_value = float(
        profile.get("portfolio_value", 0)
    )

    preferred_sectors = profile.get(
        "preferred_sectors",
        [],
    )

    if not isinstance(preferred_sectors, list):
        preferred_sectors = []

    if tolerance == "conservative":
        numeric_tolerance = 2
        max_allocation_pct = 5.0
        profile_label = "CONSERVATIVE"
    elif tolerance == "aggressive":
        numeric_tolerance = 9
        max_allocation_pct = 25.0
        profile_label = "AGGRESSIVE"
    else:
        numeric_tolerance = 5
        max_allocation_pct = 10.0
        profile_label = "UNKNOWN"

    signals = market_data.get("signals") or {}
    volume = signals.get("volume_anomaly") or {}
    sentiment = signals.get("sentiment") or {}
    momentum = signals.get("price_momentum") or {}

    risk_points = 0
    evidence: list[str] = []

    # Use actual feed classifications rather than inventing
    # beta/annualized-volatility values.
    momentum_class = str(
        momentum.get("classification", "")
    ).upper()

    if momentum_class in {"BEARISH", "NEGATIVE"}:
        risk_points += 20
        evidence.append(
            "Feed reports bearish price momentum."
        )
    elif momentum_class in {"BULLISH", "POSITIVE"}:
        evidence.append(
            "Feed reports bullish price momentum."
        )

    anomaly_ratio = volume.get("anomaly_ratio")

    if isinstance(anomaly_ratio, (int, float)):
        anomaly_ratio = float(anomaly_ratio)

        if anomaly_ratio >= 1.5 or anomaly_ratio <= 0.5:
            risk_points += 25
            evidence.append(
                f"Volume anomaly ratio is {anomaly_ratio:.2f}x."
            )

    sentiment_class = str(
        sentiment.get("classification", "")
    ).upper()

    if sentiment_class in {
        "BEARISH",
        "NEGATIVE",
        "UNAVAILABLE",
    }:
        risk_points += 15
        evidence.append(
            f"Sentiment classification is {sentiment_class or 'UNAVAILABLE'}."
        )

    # Conservative users get a lower risk capacity.
    capacity_score = numeric_tolerance * 10

    risk_score = float(
        min(
            100,
            max(
                0,
                risk_points,
            ),
        )
    )

    if risk_score <= capacity_score - 15:
        suitability = "SUITABLE"
        allocation_factor = 1.0

    elif risk_score <= capacity_score + 15:
        suitability = "CAUTION"
        allocation_factor = 0.5

    else:
        suitability = "UNSUITABLE"
        allocation_factor = 0.15

    recommended_allocation_pct = round(
        min(
            max_allocation_pct,
            max_allocation_pct * allocation_factor,
        ),
        2,
    )

    if not evidence:
        evidence.append(
            "No elevated risk indicators were detected in the supplied feed."
        )

    reasoning = (
        f"Profile={profile_label}, stored risk_tolerance="
        f"{tolerance}, portfolio_value=₹{portfolio_value:,.0f}. "
        f"Risk evidence: {' '.join(evidence)} "
        f"Risk score={risk_score}/100; capacity={capacity_score}/100; "
        f"suitability={suitability}. "
        f"Allocation capped at {max_allocation_pct}%."
    )

    return {
        "agent": "risk_profiler",
        "suitability_flag": suitability,
        "risk_score": risk_score,
        "recommended_allocation_pct": recommended_allocation_pct,
        "reasoning": reasoning,
        "input_validation": {
            "valid": True,
            "issues": [],
        },
        "profile": {
            "id": profile.get("id"),
            "risk_tolerance": tolerance,
            "portfolio_value": portfolio_value,
            "preferred_sectors": preferred_sectors,
        },
        "data_note": (
            "Risk suitability uses the live profile and supplied "
            "market-feed risk evidence. No beta or annualized "
            "volatility values were fabricated."
        ),
        "ticker": ticker,
    }


# ============================================================
# AGENT EXECUTION
# ============================================================

async def run_sameer_technical(
    ticker: str,
    market_data: dict[str, Any],
) -> dict[str, Any]:

    indicators = build_technical_input(
        market_data
    )

    result = await asyncio.to_thread(
        TECHNICAL_AGENT.run,
        indicators,
        "auto",
    )

    result["ticker"] = ticker

    return result


async def run_sameer_fundamental(
    query: str,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:

    chunks = convert_rag_chunks(
        documents
    )

    result = await asyncio.to_thread(
        FUNDAMENTAL_AGENT.run,
        {
            "query": query,
            "chunks": chunks,
        },
        "auto",
    )

    return result


async def run_risk(
    ticker: str,
    profile: dict[str, Any],
    market_data: dict[str, Any],
) -> dict[str, Any]:

    return await asyncio.to_thread(
        build_risk_result,
        profile,
        market_data,
        ticker,
    )


async def run_with_timeout(
    name: str,
    function,
    *args,
    timeout: float = AGENT_TIMEOUT,
) -> tuple[str, dict[str, Any] | None, str | None]:

    try:
        result = await asyncio.wait_for(
            function(*args),
            timeout=timeout,
        )

        return name, result, None

    except asyncio.TimeoutError:
        return (
            name,
            None,
            f"{name} agent timed out after {timeout}s",
        )

    except Exception as exc:
        return (
            name,
            None,
            f"{name} agent failed: {exc}",
        )


# ============================================================
# MULTI-AGENT PIPELINE
# ============================================================

async def execute_pipeline(
    ticker: str,
    user_profile_id: str,
    query: str,
    force_degraded: bool = False,
) -> dict[str, Any]:

    ticker = ticker.upper().strip()

    profile = get_user_profile(
        user_profile_id
    )

    market_data = load_market_feed(
        ticker
    )

    # RAG retrieval is needed by the Fundamental Agent.
    query_vector = await asyncio.to_thread(
        generate_query_embedding,
        query,
    )

    documents = await asyncio.to_thread(
        search_documents,
        query_vector,
    )

    # --------------------------------------------------------
    # Run the 3 agents concurrently.
    # --------------------------------------------------------

    tasks = [
        run_with_timeout(
            "technical",
            run_sameer_technical,
            ticker,
            market_data,
        ),
        run_with_timeout(
            "fundamental",
            run_sameer_fundamental,
            query,
            documents,
        ),
        run_with_timeout(
            "risk",
            run_risk,
            ticker,
            profile,
            market_data,
        ),
    ]

    results_list = await asyncio.gather(
        *tasks
    )

    results: dict[str, Any] = {}
    errors: list[str] = []

    for name, result, error in results_list:
        if result is None:
            results[name] = {
                "agent": name,
                "status": "failed",
                "error": error or "Unknown agent failure",
            }
        else:
            results[name] = result

        if error:
            errors.append(error)

    # --------------------------------------------------------
    # force_degraded is a demo switch.
    # --------------------------------------------------------

    if force_degraded:
        results["technical"] = {
            "agent": "technical",
            "status": "failed",
            "error": "Simulated network failure",
        }

        if "Degraded mode manually triggered." not in errors:
            errors.append(
                "Degraded mode manually triggered."
            )

    # --------------------------------------------------------
    # Sameer's deterministic synthesis.
    # --------------------------------------------------------

    synthesis = await asyncio.to_thread(
        SYNTHESIS_AGENT.synthesize,
        results.get("technical"),
        results.get("fundamental"),
        results.get("risk"),
    )

    degraded_mode = bool(
        errors
    ) or bool(
        synthesis.get("degraded_mode", False)
    )

    return {
        "profile": profile,
        "market_data": market_data,
        "documents": documents,
        "technical": results.get("technical", {}),
        "fundamental": results.get("fundamental", {}),
        "risk": results.get("risk", {}),
        "synthesis": synthesis,
        "degraded_mode": degraded_mode,
        "errors": errors,
    }


# ============================================================
# ANSWER / RISK FLAG
# ============================================================

def build_user_answer(
    pipeline: dict[str, Any],
    query: str,
) -> tuple[str, bool, list[str]]:

    fundamental = pipeline.get(
        "fundamental",
        {},
    )

    risk = pipeline.get(
        "risk",
        {},
    )

    synthesis = pipeline.get(
        "synthesis",
        {},
    )

    profile = pipeline.get(
        "profile",
        {},
    )

    citations = fundamental.get(
        "citations",
        [],
    )

    sources: list[str] = []

    for citation in citations:
        if not isinstance(citation, dict):
            continue

        source = citation.get(
            "source"
        )

        if source and source not in sources:
            sources.append(source)

    if not sources:
        for document in pipeline.get(
            "documents",
            [],
        ):
            source = document.get(
                "source_name"
            )

            if source and source not in sources:
                sources.append(source)

    summary = fundamental.get(
        "summary",
        "",
    )

    if not summary:
        summary = (
            "The fundamental agent did not return "
            "sufficient grounded context."
        )

    signal = synthesis.get(
        "signal",
        "HOLD",
    )

    risk_tolerance = str(
        profile.get(
            "risk_tolerance",
            "unknown",
        )
    ).lower()

    suitability = risk.get(
        "suitability_flag",
        "INVALID_INPUT",
    )

    risk_flag = (
        suitability in {
            "CAUTION",
            "UNSUITABLE",
            "INVALID_INPUT",
        }
        or pipeline.get("degraded_mode", False)
    )

    answer = (
        f"DataShield signal: {signal}. "
        f"{summary} "
        f"User profile is {risk_tolerance}; "
        f"risk suitability is {suitability}. "
    )

    if risk_flag:
        answer += (
            "Use caution: this output is a risk-aware analytical "
            "assessment, not a guarantee or personalized investment order."
        )
    else:
        answer += (
            "This is an analytical assessment, not a guarantee "
            "or personalized investment order."
        )

    return answer, risk_flag, sources


# ============================================================
# POST /api/query
# ============================================================

@app.post(
    "/api/query",
    response_model=QueryResponse,
)
async def api_query(
    request: QueryRequest,
):

    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail="query cannot be empty",
        )

    ticker = (
        request.ticker
        or "TATAMOTORS"
    ).upper().strip()

    try:

        pipeline = await execute_pipeline(
            ticker=ticker,
            user_profile_id=request.user_id,
            query=request.query,
            force_degraded=request.force_degraded,
        )

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {exc}",
        )

    answer, risk_flag, sources = build_user_answer(
        pipeline,
        request.query,
    )

    return QueryResponse(
        answer=answer,
        risk_flag=risk_flag,
        user_risk_category=str(
            pipeline["profile"].get(
                "risk_tolerance",
                "unknown",
            )
        ),
        sources=sources,
        technical=pipeline["technical"],
        fundamental=pipeline["fundamental"],
        risk=pipeline["risk"],
        synthesis=pipeline["synthesis"],
        degraded_mode=pipeline["degraded_mode"],
        errors=pipeline["errors"],
    )


# ============================================================
# POST /analyze
# ============================================================

@app.post(
    "/analyze",
    response_model=AnalyzeResponse,
)
async def analyze(
    request: AnalyzeRequest,
):

    query = (
        request.query
        or f"{request.ticker} financial fundamentals outlook risks"
    )

    try:

        pipeline = await execute_pipeline(
            ticker=request.ticker,
            user_profile_id=request.user_profile_id,
            query=query,
            force_degraded=request.force_degraded,
        )

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Pipeline failed: {exc}",
        )

    return AnalyzeResponse(
        ticker=request.ticker.upper().strip(),
        user_profile_id=request.user_profile_id,
        technical=pipeline["technical"],
        fundamental=pipeline["fundamental"],
        risk=pipeline["risk"],
        synthesis=pipeline["synthesis"],
        degraded_mode=pipeline["degraded_mode"],
        errors=pipeline["errors"],
    )


# ============================================================
# BASIC ENDPOINTS
# ============================================================

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "DataShield API",
        "endpoints": [
            "POST /api/query",
            "POST /analyze",
            "GET /test-db",
            "GET /health",
        ],
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
    }


# ============================================================
# DATABASE TEST
# ============================================================

@app.get("/test-db")
def test_db():

    try:

        response = (
            supabase
            .table("user_profiles")
            .select(
                "id, risk_tolerance, "
                "portfolio_value, preferred_sectors"
            )
            .eq(
                "id",
                "user_retail_safe",
            )
            .single()
            .execute()
        )

        return {
            "status": "success",
            "data": response.data,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=f"Database test failed: {exc}",
        )
