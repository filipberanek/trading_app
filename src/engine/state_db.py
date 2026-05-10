"""SQLite persistence layer for engine state.

Schema is auto-created on first use.
All timestamps are stored as UTC ISO-8601 strings.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.brokers.base_broker import Position
from src.strategies.base_strategy import Signal

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heartbeat (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    status  TEXT NOT NULL,
    message TEXT
);
CREATE TABLE IF NOT EXISTS positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    quantity     REAL NOT NULL,
    avg_cost     REAL,
    market_value REAL
);
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts              TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    action          TEXT NOT NULL,
    quantity        REAL NOT NULL,
    price           REAL,
    portfolio_value REAL,
    ibkr_order_id   TEXT,
    reason          TEXT
);
CREATE TABLE IF NOT EXISTS portfolio (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    total_value REAL NOT NULL,
    cash        REAL,
    equity      REAL
);
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL,
    metadata    TEXT,
    executed    INTEGER DEFAULT 0
);
"""


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class StateDB:
    """Write-only from the trading engine; readable by the dashboard."""

    def __init__(self, db_path: str = "data/trading.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        logger.info("StateDB ready at %s", db_path)

    # ── Write methods ──────────────────────────────────────────────────────

    def write_heartbeat(self, status: str = "OK", message: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO heartbeat (ts, status, message) VALUES (?, ?, ?)",
                (_now(), status, message),
            )

    def write_positions(self, positions: list[Position]) -> None:
        ts = _now()
        with self._conn() as conn:
            for p in positions:
                conn.execute(
                    "INSERT INTO positions (ts, symbol, quantity, avg_cost, market_value)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (ts, p.symbol, p.quantity, p.average_cost, p.market_value),
                )

    def write_trade(
        self,
        symbol: str,
        action: str,
        quantity: float,
        price: Optional[float] = None,
        portfolio_value: Optional[float] = None,
        ibkr_order_id: Optional[str] = None,
        reason: str = "",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO trades"
                " (ts, symbol, action, quantity, price, portfolio_value,"
                "  ibkr_order_id, reason)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (_now(), symbol, action, quantity, price,
                 portfolio_value, ibkr_order_id, reason),
            )

    def write_portfolio(
        self,
        total_value: float,
        cash: Optional[float] = None,
        equity: Optional[float] = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO portfolio (ts, total_value, cash, equity)"
                " VALUES (?, ?, ?, ?)",
                (_now(), total_value, cash, equity),
            )

    def write_signals(self, signals: list[Signal], executed: bool = False) -> None:
        ts = _now()
        with self._conn() as conn:
            for s in signals:
                conn.execute(
                    "INSERT INTO signals"
                    " (ts, symbol, signal_type, confidence, metadata, executed)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        ts,
                        s.symbol,
                        s.signal_type.value,
                        s.confidence,
                        json.dumps(s.metadata),
                        int(executed),
                    ),
                )

    # ── Read methods (used by dashboard / API) ─────────────────────────────

    def get_latest_heartbeat(self) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM heartbeat ORDER BY id DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def get_latest_positions(self) -> list[dict]:
        with self._conn() as conn:
            latest = conn.execute(
                "SELECT ts FROM positions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not latest:
                return []
            rows = conn.execute(
                "SELECT * FROM positions WHERE ts = ?", (latest["ts"],)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_portfolio_history(self, days: int = 365) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM portfolio ORDER BY id DESC LIMIT ?", (days,)
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_trades(self, limit: int = 200) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def get_signals(self, limit: int = 50) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    # ── Internal ───────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn
