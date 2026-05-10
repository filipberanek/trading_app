"""
Trading Bot — REST API (FastAPI)

Reads live data from the SQLite database written by the trading engine.
This API has no IBKR credentials and cannot place orders.

Run with:
    uvicorn src.api.main:app --port 8000
"""

import os
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.engine.state_db import StateDB

app = FastAPI(title="Trading Bot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_DB_PATH = os.getenv("DB_PATH", "data/trading.db")


def _db() -> StateDB:
    return StateDB(_DB_PATH)


# ── Status ────────────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status() -> dict:
    """Engine liveness: last heartbeat timestamp and status."""
    hb = _db().get_latest_heartbeat()
    if not hb:
        return {"status": "NO_DATA", "last_heartbeat": None, "message": ""}

    last_ts = datetime.fromisoformat(hb["ts"])
    age_minutes = (
        datetime.now(tz=timezone.utc) - last_ts
    ).total_seconds() / 60

    return {
        "status": hb["status"],
        "last_heartbeat": hb["ts"],
        "age_minutes": round(age_minutes, 1),
        "message": hb.get("message", ""),
        "engine_alive": age_minutes < 10,  # heartbeat every 5 min; >10 min = engine down
    }


# ── Positions ─────────────────────────────────────────────────────────────────

@app.get("/api/positions")
def get_positions() -> list[dict]:
    """Current open positions (latest snapshot)."""
    return _db().get_latest_positions()


# ── Portfolio equity curve ────────────────────────────────────────────────────

@app.get("/api/equity")
def get_equity(days: int = 365) -> list[dict]:
    """Daily portfolio value history."""
    if days < 1 or days > 3650:
        raise HTTPException(status_code=400, detail="days must be 1–3650")
    return _db().get_portfolio_history(days=days)


# ── Trades ────────────────────────────────────────────────────────────────────

@app.get("/api/trades")
def get_trades(limit: int = 200) -> list[dict]:
    """Executed trades, newest first."""
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit must be 1–1000")
    return _db().get_trades(limit=limit)


# ── Signals ───────────────────────────────────────────────────────────────────

@app.get("/api/signals")
def get_signals(limit: int = 50) -> list[dict]:
    """Generated signals (including hold / no-action cycles)."""
    return _db().get_signals(limit=limit)
