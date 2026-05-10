"""OHLCV data fetcher — wraps IBKR reqHistoricalData."""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from ib_insync import Contract, IB, util

logger = logging.getLogger(__name__)

_COL_MAP = {
    "open": "Open",
    "high": "High",
    "low": "Low",
    "close": "Close",
    "volume": "Volume",
}


class DataFetcher:
    """Fetches daily OHLCV bars from IBKR for one or more tickers.

    contract_specs maps ticker → {sec_type, exchange, currency}.
    Unknown tickers fall back to ETF / SMART / USD.
    """

    def __init__(self, ib: IB, contract_specs: dict[str, dict]) -> None:
        self._ib = ib
        self._specs = contract_specs

    def get_ohlcv(self, symbol: str, bars: int = 200) -> Optional[pd.DataFrame]:
        """Return last `bars` daily OHLCV rows for `symbol`, or None on failure."""
        spec = self._specs.get(symbol, {})
        contract = Contract(
            symbol=symbol,
            secType=spec.get("sec_type", "ETF"),
            exchange=spec.get("exchange", "SMART"),
            currency=spec.get("currency", "USD"),
        )

        try:
            self._ib.qualifyContracts(contract)
        except Exception as exc:
            logger.error("qualifyContracts failed for %s: %s", symbol, exc)
            return None

        # Request extra calendar days to account for weekends + holidays
        duration = f"{bars + 60} D"
        try:
            raw = self._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting="1 day",
                whatToShow="TRADES",
                useRTH=True,
                formatDate=1,
            )
        except Exception as exc:
            logger.error("reqHistoricalData failed for %s: %s", symbol, exc)
            return None

        if not raw:
            logger.warning("Empty historical data returned for %s", symbol)
            return None

        df = util.df(raw).rename(columns=_COL_MAP)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")[["Open", "High", "Low", "Close", "Volume"]]
        logger.debug("Fetched %d bars for %s", len(df), symbol)
        return df.tail(bars)
