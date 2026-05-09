"""
Shared OHLCV data loader for all backtest strategies.

Priority per ticker:
  1. Local CSV   data preprocessing/input_data/<TICKER>.csv
  2. IBKR TWS    requires TWS running on port 7497 (paper account)
  3. yfinance    fallback — used mainly for ^VIX and any ticker absent from both above

Public API:
  load_ohlcv(ticker, period='5y')          → pd.DataFrame  (OHLCV)
  load_all(tickers, period='5y')           → dict[str, pd.DataFrame]  (Open+Close)
  load_vix(period='5y')                    → pd.DataFrame  (VIX Close)
"""
from __future__ import annotations

import os
import re
import logging
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE    = os.path.dirname(os.path.abspath(__file__))    # experiments/initial/
_APP     = os.path.dirname(os.path.dirname(_HERE))        # trading_app/
_CSV_DIR = os.path.join(_APP, 'data_preprocessing', 'input_data')

# ── IBKR settings ─────────────────────────────────────────────────────────────

_IB_HOST      = '127.0.0.1'
_IB_PORT      = 7497          # paper account
_IB_CLIENT_ID = 10            # keep different from download_data.py (uses 1)
_IB_DURATION  = '20 Y'


# ── Period → date cutoff ──────────────────────────────────────────────────────

def _cutoff(period: str) -> pd.Timestamp | None:
    m = re.fullmatch(r'(\d+)(y|mo|d)', period.lower())
    if m is None:
        return None
    n, unit = int(m.group(1)), m.group(2)
    today = pd.Timestamp.today().normalize()
    if unit == 'y':  return today - pd.DateOffset(years=n)
    if unit == 'mo': return today - pd.DateOffset(months=n)
    return today - pd.DateOffset(days=n)


def _trim(df: pd.DataFrame, period: str) -> pd.DataFrame:
    c = _cutoff(period)
    return df.loc[c:] if c is not None else df


# ── Source 1: local CSV ───────────────────────────────────────────────────────

def _from_csv(ticker: str, period: str, csv_dir: str) -> pd.DataFrame | None:
    path = os.path.join(csv_dir, f'{ticker}.csv')
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=['Date'], index_col='Date')
    df.index = pd.to_datetime(df.index)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    if df.empty:
        return None
    return _trim(df, period)


# ── Source 2: IBKR TWS ────────────────────────────────────────────────────────

def _from_ibkr(ticker: str) -> pd.DataFrame | None:
    try:
        from ib_insync import IB, Contract, util
    except ImportError:
        return None

    ib = IB()
    try:
        ib.connect(_IB_HOST, _IB_PORT, clientId=_IB_CLIENT_ID, timeout=5)
    except Exception:
        return None

    try:
        ib_log = logging.getLogger('ib_insync')
        prev   = ib_log.level
        ib_log.setLevel(logging.CRITICAL)
        contract = None
        try:
            for currency in ('USD', 'EUR', 'GBP', ''):
                c = Contract(symbol=ticker, secType='STK', exchange='SMART', currency=currency)
                try:
                    q = ib.qualifyContracts(c)
                    if q:
                        contract = q[0]
                        break
                except Exception:
                    continue
        finally:
            ib_log.setLevel(prev)

        if contract is None:
            return None

        bars = ib.reqHistoricalData(
            contract, endDateTime='', durationStr=_IB_DURATION,
            barSizeSetting='1 day', whatToShow='TRADES',
            useRTH=True, formatDate=1,
        )
        if not bars:
            return None

        df = util.df(bars)
        if df is None or df.empty:
            return None
        df = df.rename(columns={'date': 'Date', 'open': 'Open', 'high': 'High',
                                'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.set_index('Date')
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        return df if not df.empty else None

    finally:
        ib.disconnect()


# ── Source 3: yfinance ────────────────────────────────────────────────────────

def _from_yfinance(ticker: str, period: str) -> pd.DataFrame | None:
    try:
        import yfinance as yf
    except ImportError:
        return None
    df = yf.download(ticker, period=period, progress=False)
    if df is None or df.empty:
        return None
    df = df.dropna()
    if getattr(df.columns, 'nlevels', 1) > 1:
        df.columns = df.columns.droplevel(1)
    cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in df.columns]
    df = df[cols].dropna()
    return df if not df.empty else None


# ── Public API ────────────────────────────────────────────────────────────────

def load_ohlcv(ticker: str, period: str = '5y', csv_dir: str = _CSV_DIR) -> pd.DataFrame:
    """
    Load full OHLCV for one ticker.
    Priority: local CSV → IBKR → yfinance.
    Raises ValueError if all sources fail.
    """
    df = _from_csv(ticker, period, csv_dir)
    if df is not None and not df.empty:
        return df

    print(f'  [{ticker}] not in local CSV — trying IBKR...')
    df = _from_ibkr(ticker)
    if df is not None and not df.empty:
        return _trim(df, period)

    print(f'  [{ticker}] IBKR unavailable — trying yfinance...')
    df = _from_yfinance(ticker, period)
    if df is not None and not df.empty:
        return df

    raise ValueError(f'No data found for {ticker!r} from any source (CSV / IBKR / yfinance).')


def load_all(tickers: list[str], period: str = '5y',
             csv_dir: str = _CSV_DIR) -> dict[str, pd.DataFrame]:
    """
    Load Open+Close for multiple tickers.
    Returns dict {ticker: df[['Open','Close']]}. Skips tickers that fail all sources.
    """
    result = {}
    for t in tickers:
        try:
            df = load_ohlcv(t, period=period, csv_dir=csv_dir)
            result[t] = df[['Open', 'Close']]
        except ValueError as e:
            print(f'  WARNING: {e}')
    return result


def load_vix(period: str = '5y') -> pd.DataFrame:
    """
    Load VIX index (^VIX). Always uses yfinance — no local CSV for VIX.
    Returns DataFrame with column 'VIX'.
    """
    df = _from_yfinance('^VIX', period)
    if df is None or df.empty:
        raise ValueError('Could not download VIX data from yfinance.')
    return df[['Close']].rename(columns={'Close': 'VIX'})
