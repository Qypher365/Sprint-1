import asyncio
import os
from typing import Any, List, Literal
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import create_client, Client
from google import genai
from google.genai import types

load_dotenv()

# ============================================================
# API Clients & Environment Setup
# ============================================================

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://vahhwrwezfwumbajxqzg.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_KEY else None
ai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

app = FastAPI(
    title="Multi-Agent Financial Intelligence API",
    version="1.0.0",
)

# Enable CORS for Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Divyansh / UI API Models (POST /api/query)
# ============================================================

class MetricItem(BaseModel):
    label: str = Field(description="Name of financial metric, e.g. 'Revenue growth'")
    value: str = Field(description="Formatted value, e.g. '+25%'")
    delta: str = Field(description="Time period or delta metric, e.g. 'YoY'")
    tone: Literal["up", "down", "neutral"] = Field(description="Visual sentiment indicator for UI")


class QueryRequest(BaseModel):
    query: str
    profile: Literal["conservative", "degen"] = "conservative"


class StructuredQueryResponse(BaseModel):
    risk_severity: Literal["LOW", "MEDIUM", "HIGH"]
    risk_flag: str = Field(description="1-2 sentences of contextual advice displayed under the dial")
    metrics: List[MetricItem] = Field(description="3 to 5 financial metric objects extracted from context")
    answer: str = Field(description="Detailed textual financial analysis")
    sources: List[str] = Field(description="List of source file names used for grounding")


# ============================================================
# Himanshu Multi-Agent Models (POST /analyze)
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
# Live DataShield Engine (POST /api/query)
# ============================================================

@app.post("/api/query", response_model=StructuredQueryResponse)
async def process_query(req: QueryRequest):
    if not supabase or not ai_client:
        raise HTTPException(
            status_code=500, 
            detail="Backend uninitialized: Missing SUPABASE_KEY or GEMINI_API_KEY."
        )

    try:
        # Step 1: Embed Query using Gemini Embeddings (768-dim)
        embed_res = ai_client.models.embed_content(
            model="gemini-embedding-001",
            contents=req.query,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768
            )
        )
        query_vector = embed_res.embeddings[0].values

        # Step 2: Supabase pgvector Similarity Search
        rpc_res = supabase.rpc(
            "match_documents",
            {
                "query_embedding": query_vector,
                "match_threshold": 0.1,
                "match_count": 3
            }
        ).execute()

        retrieved_chunks = rpc_res.data or []
        context_text = "\n---\n".join([chunk.get("content", "") for chunk in retrieved_chunks])
        source_names = list(set([chunk.get("source_name", "TATA_MOTORS_Q3_FY24") for chunk in retrieved_chunks])) or ["TATA_MOTORS_Q3_FY24"]

        # Step 3: Dynamic Profile Instructions
        if req.profile == "degen":
            profile_instruction = (
                "USER PROFILE: Aggressive F&O / Derivatives Trader. "
                "High risk tolerance for short-term price movements, but strictly highlight liquidity traps, "
                "extreme volatility, and supply chain disruptions (e.g., Red Sea risks). "
                "Set risk_severity to 'MEDIUM' for speculative momentum trades unless structural risk is critical."
            )
        else:
            profile_instruction = (
                "USER PROFILE: Conservative Long-Term Investor. "
                "Prioritizes capital preservation and debt reduction. Strictly flag high leverage, options exposure, "
                "and supply chain bottlenecks. "
                "Set risk_severity to 'HIGH' if the query implies short-term leverage or unhedged options positions."
            )

        system_instruction = f"""
        You are DataShield's AI Financial Risk Engine.
        Use ONLY the provided GROUNDING CONTEXT to evaluate the user's trading question.
        
        {profile_instruction}

        GROUNDING CONTEXT:
        {context_text}
        """

        # Step 4: Structured Reasoning Generation via Gemini 2.5 Flash
        gen_response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"User Question: {req.query}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=StructuredQueryResponse,
                temperature=0.2
            )
        )

        result = StructuredQueryResponse.model_validate_json(gen_response.text)
        result.sources = source_names
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Multi-Agent Framework Functions (POST /analyze)
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


async def synthesize(results: dict[str, Any]) -> dict[str, Any]:
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
# Endpoints: Health Check & Multi-Agent Analyze
# ============================================================

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Multi-Agent Financial Intelligence API"
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    errors: list[str] = []

    tasks = [
        run_agent("technical", technical_agent, request.ticker),
        run_agent("fundamental", fundamental_agent, request.ticker),
        run_agent("risk", risk_agent, request.ticker, request.user_profile_id),
    ]

    results_list = await asyncio.gather(*tasks)
    results = {}

    for name, result, error in results_list:
        results[name] = result
        if error:
            errors.append(error)

    if request.force_degraded:
        errors.append("Degraded mode manually triggered.")
        results["technical"] = {
            "agent": "technical",
            "status": "failed",
            "error": "Simulated network failure"
        }

    degraded_mode = len(errors) > 0
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
