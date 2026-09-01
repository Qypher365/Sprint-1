"""
Mock Market Data Service — PS-01 Sprint 1

Serves the three static JSON feeds as HTTP endpoints so your agent layer
(CrewAI/LangChain) can call this exactly like it would call a real NSE feed
or a market-data provider. This is what makes the demo look "live" even
though the underlying data is static.

Run:
    uvicorn mock_market_service:app --reload --port 8001

Endpoints:
    GET /feed/{symbol}                 -> tatamotors | reliance | infosys
    GET /feed/{symbol}?jitter=true      -> adds small random noise to price
                                           fields each call, so repeated demo
                                           runs don't look byte-identical
    GET /symbols                       -> list of available symbols
"""

import json
import random
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATA_DIR = Path(__file__).parent / "data"

SYMBOL_TO_FILE = {
    "tatamotors": "tata_motors_feed.json",
    "reliance": "reliance_feed.json",
    "infosys": "infosys_feed.json",
}

app = FastAPI(title="PS-01 Mock Market Feed")

# Allow your frontend (React/Streamlit/whatever) to call this from the browser
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_feed(symbol: str) -> dict:
    filename = SYMBOL_TO_FILE.get(symbol.lower())
    if not filename:
        raise HTTPException(status_code=404, detail=f"Unknown symbol '{symbol}'")
    path = DATA_DIR / filename
    with open(path, "r") as f:
        return json.load(f)


def _apply_jitter(feed: dict) -> dict:
    """Nudge price fields by a small random % so re-running live on stage
    doesn't show the exact same numbers every time. Signal classifications
    and the degraded/conflict scenarios are left untouched on purpose."""
    price = feed.get("price_data", {})
    for key in ("last_traded_price", "day_change_pct"):
        if key in price and isinstance(price[key], (int, float)):
            price[key] = round(price[key] * (1 + random.uniform(-0.004, 0.004)), 2)
    return feed


@app.get("/symbols")
def list_symbols():
    return {"symbols": list(SYMBOL_TO_FILE.keys())}


@app.get("/feed/{symbol}")
def get_feed(symbol: str, jitter: Optional[bool] = False):
    feed = _load_feed(symbol)
    if jitter:
        feed = _apply_jitter(feed)
    return feed
