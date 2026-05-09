"""Unit tests for AtrSmaCStrategy.

Tests cover:
  - Parameter validation
  - Entry signal (close above upper ATR band)
  - Exit signal (close below lower ATR band)
  - Hold (close inside band)
  - Alt selection by trend strength
  - Cash fallback (all alts below SMA)
  - Insufficient data guard
  - Position sizing (100% allocation)
"""

import numpy as np
import pandas as pd
import pytest

from src.strategies.atr_sma_c import CASH, AtrSmaCStrategy, MarketSnapshot
from src.strategies.base_strategy import SignalType

# ── Fixtures ───────────────────────────────────────────────────────────────────

PARAMS = {
    "sma_window": 5,
    "atr_window": 3,
    "atr_multiplier": 0.5,
    "main_ticker": "EQQQ",
}


def _make_ohlcv(closes: list[float], spread: float = 0.5) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a close price series."""
    closes = np.array(closes, dtype=float)
    return pd.DataFrame({
        "Open":   closes * 0.999,
        "High":   closes + spread,
        "Low":    closes - spread,
        "Close":  closes,
        "Volume": np.ones(len(closes)) * 1_000,
    }, index=pd.date_range("2024-01-01", periods=len(closes), freq="B"))


def _trending_up(n: int = 20, start: float = 100.0) -> pd.DataFrame:
    """Steadily rising prices — close will be well above SMA."""
    closes = [start + i * 2 for i in range(n)]
    return _make_ohlcv(closes)


def _trending_down(n: int = 20, start: float = 100.0) -> pd.DataFrame:
    """Steadily falling prices — close will be well below SMA."""
    closes = [start - i * 2 for i in range(n)]
    return _make_ohlcv(closes)


def _flat(n: int = 20, price: float = 100.0) -> pd.DataFrame:
    """Flat prices — close stays on SMA, stays inside band."""
    return _make_ohlcv([price] * n)


@pytest.fixture
def strategy() -> AtrSmaCStrategy:
    return AtrSmaCStrategy(PARAMS)


# ── Parameter validation ───────────────────────────────────────────────────────

def test_invalid_sma_window_raises():
    with pytest.raises(ValueError, match="sma_window"):
        AtrSmaCStrategy({**PARAMS, "sma_window": 1})


def test_invalid_atr_window_raises():
    with pytest.raises(ValueError, match="atr_window"):
        AtrSmaCStrategy({**PARAMS, "atr_window": 0})


def test_invalid_atr_multiplier_raises():
    with pytest.raises(ValueError, match="atr_multiplier"):
        AtrSmaCStrategy({**PARAMS, "atr_multiplier": -0.1})


def test_valid_parameters_no_error():
    AtrSmaCStrategy(PARAMS)  # must not raise


# ── Insufficient data ─────────────────────────────────────────────────────────

def test_insufficient_data_returns_empty(strategy):
    tiny_df = _flat(n=3)  # less than warmup
    snapshot = MarketSnapshot(main_ohlcv=tiny_df, alt_ohlcv={}, current_position=CASH)
    assert strategy.generate_signals(snapshot) == []


# ── Entry signal ──────────────────────────────────────────────────────────────

def test_entry_signal_when_above_band(strategy):
    df = _trending_up(n=20)
    snapshot = MarketSnapshot(main_ohlcv=df, alt_ohlcv={}, current_position=CASH)
    signals = strategy.generate_signals(snapshot)

    assert len(signals) == 1
    assert signals[0].symbol == "EQQQ"
    assert signals[0].signal_type == SignalType.BUY


def test_no_entry_when_already_in_main(strategy):
    df = _trending_up(n=20)
    snapshot = MarketSnapshot(main_ohlcv=df, alt_ohlcv={}, current_position="EQQQ")
    signals = strategy.generate_signals(snapshot)
    assert signals == []


# ── Exit signal ───────────────────────────────────────────────────────────────

def test_exit_to_cash_when_below_band_no_alts(strategy):
    df = _trending_down(n=20)
    snapshot = MarketSnapshot(
        main_ohlcv=df, alt_ohlcv={}, current_position="EQQQ"
    )
    signals = strategy.generate_signals(snapshot)

    assert len(signals) == 1
    assert signals[0].symbol == "EQQQ"
    assert signals[0].signal_type == SignalType.SELL


def test_exit_to_alt_when_alt_trending(strategy):
    df = _trending_down(n=20)
    alt_trending = _trending_up(n=20, start=50.0)
    snapshot = MarketSnapshot(
        main_ohlcv=df,
        alt_ohlcv={"IGLN": alt_trending},
        current_position="EQQQ",
    )
    signals = strategy.generate_signals(snapshot)

    assert len(signals) == 2
    assert signals[0].symbol == "EQQQ"
    assert signals[0].signal_type == SignalType.SELL
    assert signals[1].symbol == "IGLN"
    assert signals[1].signal_type == SignalType.BUY


def test_no_exit_when_not_in_main(strategy):
    df = _trending_down(n=20)
    snapshot = MarketSnapshot(
        main_ohlcv=df, alt_ohlcv={}, current_position=CASH
    )
    assert strategy.generate_signals(snapshot) == []


# ── Hold ──────────────────────────────────────────────────────────────────────

def test_hold_when_inside_band(strategy):
    df = _flat(n=20)
    for position in (CASH, "EQQQ"):
        snapshot = MarketSnapshot(main_ohlcv=df, alt_ohlcv={}, current_position=position)
        assert strategy.generate_signals(snapshot) == [], f"Expected HOLD for position={position}"


# ── Alt selection ─────────────────────────────────────────────────────────────

def test_alt_selection_picks_strongest_trend(strategy):
    df = _trending_down(n=20)
    # IGLN rises +4/day → higher (close-SMA)/ATR than IUES at +1/day
    alt_strong = _make_ohlcv([50.0 + i * 4 for i in range(20)])
    alt_weak   = _make_ohlcv([50.0 + i * 1 for i in range(20)])

    snapshot = MarketSnapshot(
        main_ohlcv=df,
        alt_ohlcv={"IUES": alt_weak, "IGLN": alt_strong},
        current_position="EQQQ",
    )
    signals = strategy.generate_signals(snapshot)
    buy_signal = next(s for s in signals if s.signal_type == SignalType.BUY)
    assert buy_signal.symbol == "IGLN"


def test_cash_fallback_when_all_alts_below_sma(strategy):
    df = _trending_down(n=20)
    alt_falling = _trending_down(n=20, start=50.0)

    snapshot = MarketSnapshot(
        main_ohlcv=df,
        alt_ohlcv={"IUES": alt_falling},
        current_position="EQQQ",
    )
    signals = strategy.generate_signals(snapshot)

    assert len(signals) == 1
    assert signals[0].signal_type == SignalType.SELL
    assert signals[0].symbol == "EQQQ"


def test_alt_with_insufficient_data_skipped(strategy):
    df = _trending_down(n=20)
    tiny_alt = _flat(n=3)  # too short for warmup

    snapshot = MarketSnapshot(
        main_ohlcv=df,
        alt_ohlcv={"IGLN": tiny_alt},
        current_position="EQQQ",
    )
    signals = strategy.generate_signals(snapshot)
    # IGLN skipped → fallback to cash
    assert all(s.signal_type == SignalType.SELL for s in signals)


# ── Entry from alt position ───────────────────────────────────────────────────

def test_entry_from_alt_sells_alt_first(strategy):
    df = _trending_up(n=20)
    snapshot = MarketSnapshot(
        main_ohlcv=df, alt_ohlcv={}, current_position="IGLN"
    )
    signals = strategy.generate_signals(snapshot)

    assert len(signals) == 2
    assert signals[0].symbol == "IGLN"
    assert signals[0].signal_type == SignalType.SELL
    assert signals[1].symbol == "EQQQ"
    assert signals[1].signal_type == SignalType.BUY


# ── Position sizing ───────────────────────────────────────────────────────────

def test_position_size_full_allocation(strategy):
    from src.strategies.base_strategy import Signal, SignalType
    signal = Signal(symbol="EQQQ", signal_type=SignalType.BUY, confidence=1.0)
    pos = strategy.calculate_position_size(signal, portfolio_value=10_000.0, current_price=400.0)

    assert pos.symbol == "EQQQ"
    assert abs(pos.quantity - 25.0) < 1e-9   # 10000 / 400
    assert pos.max_risk_amount == 10_000.0


def test_position_size_zero_price_raises(strategy):
    from src.strategies.base_strategy import Signal, SignalType
    signal = Signal(symbol="EQQQ", signal_type=SignalType.BUY, confidence=1.0)
    with pytest.raises(ValueError):
        strategy.calculate_position_size(signal, portfolio_value=10_000.0, current_price=0.0)
