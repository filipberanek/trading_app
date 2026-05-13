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
        if symbol not in self._specs:
            raise KeyError(
                f"No contract spec for '{symbol}' — add it to the contracts section in config YAML"
            )
        spec = self._specs[symbol]
        try:
            sec_type = spec["sec_type"]
            exchange = spec["exchange"]
            currency = spec["currency"]
        except KeyError as exc:
            raise KeyError(
                f"Contract spec for '{symbol}' is missing required field {exc} "
                f"— check config YAML"
            ) from exc
        contract = Contract(
            symbol=symbol,
            secType=sec_type,
            exchange=exchange,
            currency=currency,
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
        # LSE ETFs are quoted in pence (GBX); convert to GBP
        if currency == "GBP":
            for col in ["Open", "High", "Low", "Close"]:
                df[col] = df[col] / 100
        logger.debug("Fetched %d bars for %s", len(df), symbol)
        return df.tail(bars)
