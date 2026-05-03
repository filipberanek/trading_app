"""
Trading Bot — REST API (FastAPI)

Dummy data only. Replace the _SEGMENTS / _TRADES / _EQUITY constants
and the get_status() body with real IBKR broker calls when ready.

Run with:
    uvicorn src.api.main:app --reload --port 8000
"""

from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Trading Bot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Dummy constants ───────────────────────────────────────────────────────────

_START = datetime(2023, 1, 2)
_TODAY = datetime.today().strftime("%Y-%m-%d")

_SEGMENTS = [
    {"asset": "EQQQ", "start": "2023-01-02", "end": "2023-04-14"},
    {"asset": "CASH", "start": "2023-04-17", "end": "2023-05-05"},
    {"asset": "EQQQ", "start": "2023-05-08", "end": "2023-09-22"},
    {"asset": "IUCS", "start": "2023-09-25", "end": "2023-11-10"},
    {"asset": "EQQQ", "start": "2023-11-13", "end": "2024-03-08"},
    {"asset": "IGLN", "start": "2024-03-11", "end": "2024-04-19"},
    {"asset": "EQQQ", "start": "2024-04-22", "end": "2024-08-02"},
    {"asset": "CASH", "start": "2024-08-05", "end": "2024-09-13"},
    {"asset": "IBZL", "start": "2024-09-16", "end": "2024-11-29"},
    {"asset": "EQQQ", "start": "2024-12-02", "end": _TODAY},
]

_TRADES = [
    {
        "asset": "EQQQ",
        "entry_date": "2023-01-02", "entry_price": 256.40,
        "exit_date": "2023-04-14",  "exit_price": 312.80,
        "pnl": 2201.6, "return_pct": 22.0, "held_days": 71,
    },
    {
        "asset": "CASH",
        "entry_date": "2023-04-17", "entry_price": None,
        "exit_date": "2023-05-05",  "exit_price": None,
        "pnl": 4.1, "return_pct": 0.04, "held_days": 14,
    },
    {
        "asset": "EQQQ",
        "entry_date": "2023-05-08", "entry_price": 310.10,
        "exit_date": "2023-09-22",  "exit_price": 284.30,
        "pnl": -1023.4, "return_pct": -8.3, "held_days": 99,
    },
    {
        "asset": "IUCS",
        "entry_date": "2023-09-25", "entry_price": 78.50,
        "exit_date": "2023-11-10",  "exit_price": 85.20,
        "pnl": 854.2, "return_pct": 8.5, "held_days": 33,
    },
    {
        "asset": "EQQQ",
        "entry_date": "2023-11-13", "entry_price": 290.00,
        "exit_date": "2024-03-08",  "exit_price": 395.60,
        "pnl": 3640.9, "return_pct": 36.4, "held_days": 83,
    },
    {
        "asset": "IGLN",
        "entry_date": "2024-03-11", "entry_price": 195.40,
        "exit_date": "2024-04-19",  "exit_price": 212.80,
        "pnl": 890.0, "return_pct": 8.9, "held_days": 29,
    },
    {
        "asset": "EQQQ",
        "entry_date": "2024-04-22", "entry_price": 403.20,
        "exit_date": "2024-08-02",  "exit_price": 380.50,
        "pnl": -563.2, "return_pct": -5.6, "held_days": 74,
    },
    {
        "asset": "CASH",
        "entry_date": "2024-08-05", "entry_price": None,
        "exit_date": "2024-09-13",  "exit_price": None,
        "pnl": 12.3, "return_pct": 0.12, "held_days": 29,
    },
    {
        "asset": "IBZL",
        "entry_date": "2024-09-16", "entry_price": 42.10,
        "exit_date": "2024-11-29",  "exit_price": 38.30,
        "pnl": -451.8, "return_pct": -9.0, "held_days": 54,
    },
    {
        "asset": "EQQQ",
        "entry_date": "2024-12-02", "entry_price": 390.10,
        "exit_date": None,          "exit_price": None,
        "pnl": None, "return_pct": None, "held_days": None,
    },
]


def _build_equity() -> list[dict]:
    dates = pd.date_range(_START, datetime.today(), freq="B")
    rng = np.random.default_rng(42)
    daily_ret = rng.normal(0.00045, 0.011, len(dates))
    equity = 10_000.0 * np.cumprod(1 + daily_ret)
    return [
        {"date": str(d.date()), "value": round(float(v), 2)}
        for d, v in zip(dates, equity)
    ]


_EQUITY = _build_equity()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status() -> dict:
    return {
        "strategy": "ATR-SMA — Cash Inclusive",
        "current_asset": "EQQQ",
        "allocation_pct": 0.95,
        "account_value": _EQUITY[-1]["value"],
        "running_since": "2023-01-02",
    }


@app.get("/api/equity")
def get_equity() -> list[dict]:
    return _EQUITY


@app.get("/api/allocation")
def get_allocation() -> list[dict]:
    return _SEGMENTS


@app.get("/api/trades")
def get_trades() -> list[dict]:
    return _TRADES
