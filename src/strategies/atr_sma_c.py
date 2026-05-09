"""
ATR-SMA-C strategy — broker-agnostic signal generator.

Logic:
  1. Compute SMA and ATR band for main ticker (EQQQ).
  2. EXIT signal : close < SMA * (1 - ATR/close * multiplier)
  3. ENTRY signal: close > SMA * (1 + ATR/close * multiplier)
  4. Alt selection: pick alt with highest (close - SMA) / ATR > 0.
     If none qualifies → signal CASH.

Input : MarketSnapshot (plain DataFrames, no broker dependency).
Output: list[Signal]  — caller decides how to execute.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .base_strategy import BaseStrategy, PositionSize, Signal, SignalType

logger = logging.getLogger(__name__)

CASH = "CASH"


@dataclass
class MarketSnapshot:
    """Price data needed for one signal evaluation cycle.

    main_ohlcv : OHLCV DataFrame for the main ticker.
                 Must have columns Open, High, Low, Close.
                 Must contain at least max(sma_window, atr_window) + 1 rows.
    alt_ohlcv  : Dict of OHLCV DataFrames keyed by ticker symbol.
    current_position: Ticker currently held, or 'CASH'.
    """

    main_ohlcv: pd.DataFrame
    alt_ohlcv: dict[str, pd.DataFrame]
    current_position: str = CASH


class AtrSmaCStrategy(BaseStrategy):
    """ATR-band SMA trend strategy with trend-strength alt rotation."""

    def __init__(self, parameters: dict) -> None:
        super().__init__("ATR-SMA-C", parameters)

    # ── BaseStrategy interface ─────────────────────────────────────────────

    def validate_parameters(self) -> None:
        p = self.parameters
        if p.get("sma_window", 0) < 2:
            raise ValueError("sma_window must be >= 2")
        if p.get("atr_window", 0) < 2:
            raise ValueError("atr_window must be >= 2")
        if p.get("atr_multiplier", 0) <= 0:
            raise ValueError("atr_multiplier must be > 0")

    def generate_signals(self, data: MarketSnapshot) -> list[Signal]:  # type: ignore[override]
        """Return signals for next bar execution.

        Returns empty list → hold current position.
        SELL + BUY       → rotate (execute in this order).
        Single SELL      → move to cash.
        Single BUY       → enter from cash.
        """
        sma_w = self.parameters["sma_window"]
        atr_w = self.parameters["atr_window"]
        mult  = self.parameters["atr_multiplier"]
        warmup = max(sma_w, atr_w)

        df = data.main_ohlcv
        if len(df) <= warmup:
            logger.warning("Insufficient data (%d rows, need >%d)", len(df), warmup)
            return []

        sma  = df["Close"].rolling(sma_w).mean()
        atr  = self._compute_atr(df, atr_w)
        band = atr / df["Close"] * mult

        last_close = float(df["Close"].iloc[-1])
        last_sma   = float(sma.iloc[-1])
        last_band  = float(band.iloc[-1])

        if pd.isna(last_sma) or pd.isna(last_band):
            return []

        upper = last_sma * (1 + last_band)
        lower = last_sma * (1 - last_band)
        in_main = data.current_position not in (CASH,) and data.current_position == self._main_ticker

        # ── EXIT main ticker ───────────────────────────────────────────────
        if in_main and last_close < lower:
            signals = [Signal(
                symbol=self._main_ticker,
                signal_type=SignalType.SELL,
                confidence=1.0,
                metadata={"reason": "below_atr_band", "close": last_close, "lower_band": lower},
            )]
            best_alt = self._select_alt(data.alt_ohlcv, sma_w, atr_w)
            if best_alt is not None:
                signals.append(Signal(
                    symbol=best_alt,
                    signal_type=SignalType.BUY,
                    confidence=1.0,
                    metadata={"reason": "alt_trend_strength"},
                ))
            logger.info("EXIT %s → %s", self._main_ticker, best_alt or CASH)
            return signals

        # ── ENTRY main ticker ──────────────────────────────────────────────
        if not in_main and last_close > upper:
            signals = []
            if data.current_position != CASH:
                signals.append(Signal(
                    symbol=data.current_position,
                    signal_type=SignalType.SELL,
                    confidence=1.0,
                    metadata={"reason": "rotate_to_main"},
                ))
            signals.append(Signal(
                symbol=self._main_ticker,
                signal_type=SignalType.BUY,
                confidence=1.0,
                metadata={"reason": "above_atr_band", "close": last_close, "upper_band": upper},
            ))
            logger.info("ENTRY %s (from %s)", self._main_ticker, data.current_position)
            return signals

        return []

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_price: float,
    ) -> PositionSize:
        """Always allocate 100 % of portfolio to a single position."""
        if current_price <= 0:
            raise ValueError(f"current_price must be > 0, got {current_price}")
        quantity = portfolio_value / current_price
        return PositionSize(
            symbol=signal.symbol,
            quantity=quantity,
            max_risk_amount=portfolio_value,
            rationale="100% allocation — single-asset rotation strategy",
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @property
    def _main_ticker(self) -> str:
        return self.parameters.get("main_ticker", "EQQQ")

    @staticmethod
    def _compute_atr(df: pd.DataFrame, window: int) -> pd.Series:
        prev_close = df["Close"].shift(1)
        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - prev_close).abs(),
            (df["Low"]  - prev_close).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(window).mean()

    def _select_alt(
        self,
        alt_ohlcv: dict[str, pd.DataFrame],
        sma_w: int,
        atr_w: int,
    ) -> str | None:
        """Return alt with highest trend strength > 0, or None (= cash)."""
        warmup = max(sma_w, atr_w)
        scores: dict[str, float] = {}

        for ticker, df in alt_ohlcv.items():
            if len(df) <= warmup:
                continue
            sma = df["Close"].rolling(sma_w).mean().iloc[-1]
            atr = self._compute_atr(df, atr_w).iloc[-1]
            if pd.isna(sma) or pd.isna(atr) or atr == 0:
                continue
            scores[ticker] = (float(df["Close"].iloc[-1]) - float(sma)) / float(atr)

        if not scores:
            return None
        best = max(scores, key=scores.__getitem__)
        return best if scores[best] > 0 else None
