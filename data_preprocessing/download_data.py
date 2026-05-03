"""
Download historical OHLCV data for all listed Xetra ETFs via Interactive Brokers TWS API.

Requirements:
    pip install ib_insync
    TWS must be running with API enabled on port 7497 (paper account)

Data source : IBKR TWS (Xetra exchange, EUR)
Output      : input_data/<TICKER>.csv  — only tickers with >= MIN_YEARS years,
              all trimmed to a common start date
              input_data/coverage_histogram.png

Alignment logic:
  1. Hard floor: skip tickers with < MIN_YEARS (4y) of raw data.
  2. common_start = max(first_date) across kept tickers.
     All CSVs are trimmed to this date so every file covers the same range.

Usage:
    python download_data.py
    python download_data.py --out-dir /path/to/dir
"""
from __future__ import annotations

import os
import time
import logging
import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from ib_insync import IB, Contract, util

# ── Ticker registry ──────────────────────────────────────────────────────────

SECTOR_ETFS: dict[str, str] = {
    'IUIT': 'iShares S&P 500 IT Sector UCITS',
    'IUHF': 'iShares S&P 500 Financials Sector UCITS',
    'IUHC': 'iShares S&P 500 Health Care UCITS',
    'IUES': 'iShares S&P 500 Energy UCITS',
    'IUCD': 'iShares S&P 500 Consumer Discret. UCITS',
    'IUCS': 'iShares S&P 500 Consumer Staples UCITS',
    'IUIN': 'iShares S&P 500 Industrials UCITS',
    'IUUT': 'iShares S&P 500 Utilities UCITS',
    'IUMB': 'iShares S&P 500 Materials UCITS',
}

COUNTRY_ETFS: dict[str, str] = {
    'IJPA': 'iShares Core MSCI Japan UCITS',
    'IEEM': 'iShares Core MSCI EM UCITS',
    'CEEM': 'iShares MSCI China UCITS',
    'EWG2': 'iShares MSCI Germany UCITS',
    'IBZL': 'iShares MSCI Brazil UCITS',
    'SMEA': 'iShares Core MSCI Europe UCITS',
    'VWCE': 'Vanguard FTSE All-World UCITS',
    'EEA':  'iShares MSCI Eastern Europe Capped',
}

ASSET_CLASS_ETFS: dict[str, str] = {
    'SXR8': 'iShares Core S&P 500 UCITS (Acc)',
    'EQQQ': 'Invesco NASDAQ-100 UCITS',
    'IGLN': 'iShares Physical Gold ETC',
    'IDTL': 'iShares $ Treasury Bond 20+yr UCITS',
    'IBTM': 'iShares $ Treasury Bond 7-10yr UCITS',
    'SEGA': 'SPDR Bloomberg Euro Aggregate Bond',
    'DBZB': 'Xtrackers II EUR Govt Bond UCITS',
}

ALL_TICKERS: dict[str, str] = {**SECTOR_ETFS, **COUNTRY_ETFS, **ASSET_CLASS_ETFS}

# ── IBKR connection settings ─────────────────────────────────────────────────

IB_HOST       = '127.0.0.1'
IB_PORT       = 7497   # 7497 = paper account, 7496 = live account
IB_CLIENT_ID  = 1
REQUEST_DELAY = 3      # seconds between requests (IBKR pacing: max 60 req / 10 min)
DURATION      = '20 Y' # max history available for 1-day bars

MIN_YEARS = 9

# ── Download helpers ─────────────────────────────────────────────────────────

def _years(df: pd.DataFrame) -> float:
    return (df.index[-1] - df.index[0]).days / 365.25


def _bars_to_df(bars) -> pd.DataFrame | None:
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


def _find_contract(ib: IB, ticker: str):
    """
    Try to qualify the contract directly using multiple exchange/secType combinations.
    Priority: LSE ETF → IBIS2 ETF → LSE STK → SMART ETF
    qualifyContracts fills in conId and currency; returns empty list if not found.
    """
    # Only STK (IBKR API rejects ETF secType for these instruments).
    # Only SMART (IBIS2 requires a paid Xetra market data subscription).
    # Try specific currencies first to avoid ambiguous contract errors.
    ib_logger = logging.getLogger('ib_insync')
    original_level = ib_logger.level
    ib_logger.setLevel(logging.CRITICAL)  # silence Error 200 from failed currency attempts
    try:
        for currency in ('USD', 'EUR', 'GBP', ''):
            c = Contract(symbol=ticker, secType='STK', exchange='SMART', currency=currency)
            try:
                qualified = ib.qualifyContracts(c)
                if qualified:
                    return qualified[0]
            except Exception:
                continue
    finally:
        ib_logger.setLevel(original_level)
    return None


def download_ticker(ib: IB, contract) -> pd.DataFrame | None:
    bars = ib.reqHistoricalData(
        contract,
        endDateTime='',
        durationStr=DURATION,
        barSizeSetting='1 day',
        whatToShow='TRADES',
        useRTH=True,
        formatDate=1,
    )
    return _bars_to_df(bars) if bars else None


# ── Plot ─────────────────────────────────────────────────────────────────────

def save_histogram(coverage_all: dict[str, float], coverage_kept: dict[str, float],
                   effective_years: float, out_dir: str) -> str:
    sorted_items = sorted(coverage_all.items(), key=lambda x: x[1], reverse=True)
    tickers = [t for t, _ in sorted_items]
    years   = [y for _, y in sorted_items]
    colors  = ['steelblue' if t in coverage_kept else 'salmon' for t in tickers]

    fig, (ax_bar, ax_hist) = plt.subplots(
        2, 1, figsize=(14, 9),
        gridspec_kw={'height_ratios': [3, 1.5]}
    )

    bars = ax_bar.bar(tickers, years, color=colors, edgecolor='white', linewidth=0.5)
    ax_bar.axhline(MIN_YEARS, color='red', linestyle='--', linewidth=1.2,
                   label=f'Hard floor  {MIN_YEARS}y')
    if abs(effective_years - MIN_YEARS) > 0.1:
        ax_bar.axhline(effective_years, color='darkorange', linestyle='--', linewidth=1.2,
                       label=f'Effective cutoff  {effective_years:.1f}y')
    ax_bar.set_title('Raw data coverage per ETF  (blue = kept, red = skipped)')
    ax_bar.set_ylabel('Years of raw data')
    ax_bar.tick_params(axis='x', rotation=55)
    ax_bar.grid(axis='y', alpha=0.4)
    ax_bar.legend()
    for bar, y in zip(bars, years):
        ax_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                    f'{y:.1f}', ha='center', va='bottom', fontsize=7)

    bins = np.arange(0, max(years) + 2, 1)
    ax_hist.hist(years, bins=bins, color='steelblue', edgecolor='white', linewidth=0.5)
    ax_hist.axvline(MIN_YEARS, color='red', linestyle='--', linewidth=1.2,
                    label=f'Hard floor {MIN_YEARS}y')
    if abs(effective_years - MIN_YEARS) > 0.1:
        ax_hist.axvline(effective_years, color='darkorange', linestyle='--', linewidth=1.2,
                        label=f'Effective {effective_years:.1f}y')
    ax_hist.set_title('Distribution of raw coverage lengths')
    ax_hist.set_xlabel('Years of data')
    ax_hist.set_ylabel('# tickers')
    ax_hist.grid(axis='y', alpha=0.4)
    ax_hist.legend()

    fig.tight_layout()
    path = os.path.join(out_dir, 'coverage_histogram.png')
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


# ── Main ─────────────────────────────────────────────────────────────────────

def run(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)

    ib = IB()
    print(f'Connecting to TWS  {IB_HOST}:{IB_PORT}  clientId={IB_CLIENT_ID} ...')
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID)
    print('Connected.\n')

    raw_dfs:      dict[str, pd.DataFrame] = {}
    coverage_all: dict[str, float]        = {}
    skipped:      list[str]               = []
    total = len(ALL_TICKERS)

    try:
        # ── Phase 1: download everything ─────────────────────────────────────
        for i, (ticker, name) in enumerate(ALL_TICKERS.items(), 1):
            print(f'[{i:2}/{total}]  {ticker:<6} {name[:48]}', end='  ')

            contract = _find_contract(ib, ticker)
            if contract is None:
                print('NO CONTRACT FOUND')
                skipped.append(ticker)
                time.sleep(REQUEST_DELAY)
                continue

            ibkr_label = f'{contract.symbol}@{getattr(contract, "primaryExch", "") or contract.exchange}/{contract.currency}'
            df = download_ticker(ib, contract)

            if df is None:
                print(f'NO DATA  [{ibkr_label}]')
                skipped.append(ticker)
                time.sleep(REQUEST_DELAY)
                continue

            yrs = _years(df)
            coverage_all[ticker] = yrs

            if yrs < MIN_YEARS:
                print(f'SKIP  ({yrs:.1f}y < {MIN_YEARS}y)  [{ibkr_label}]')
                skipped.append(ticker)
                time.sleep(REQUEST_DELAY)
                continue

            raw_dfs[ticker] = df
            print(f'raw  {yrs:.1f}y  [{ibkr_label}]')
            time.sleep(REQUEST_DELAY)

    finally:
        ib.disconnect()
        print('\nDisconnected from TWS.')

    # ── Phase 2: find common start ────────────────────────────────────────────
    if not raw_dfs:
        print('No tickers passed the hard floor — nothing saved.')
        return

    common_start    = max(df.index[0] for df in raw_dfs.values())
    effective_years = min(_years(df.loc[common_start:]) for df in raw_dfs.values())

    sep = '=' * 60
    print(f'\n{sep}')
    print(f'Common start date  : {common_start.date()}')
    print(f'Effective coverage : {effective_years:.1f} years  '
          f'({"= hard floor" if abs(effective_years - MIN_YEARS) < 0.1 else f"auto-adjusted from {MIN_YEARS}y floor"})')

    # ── Phase 3: trim and save ────────────────────────────────────────────────
    saved: dict[str, float] = {}
    for ticker, df in raw_dfs.items():
        trimmed  = df.loc[common_start:]
        yrs_trim = _years(trimmed)
        csv_path = os.path.join(out_dir, f'{ticker}.csv')
        trimmed.to_csv(csv_path)
        saved[ticker] = yrs_trim
        print(f'  {ticker:<6} {yrs_trim:.1f}y  →  {os.path.basename(csv_path)}')

    # ── Summary ───────────────────────────────────────────────────────────────
    if coverage_all:
        best  = max(coverage_all, key=coverage_all.get)
        print(f'\nLongest raw history : {best:<6} {coverage_all[best]:.1f}y  — {ALL_TICKERS[best]}')
    if saved:
        worst = min(saved, key=saved.get)
        print(f'Shortest kept       : {worst:<6} {saved[worst]:.1f}y  — {ALL_TICKERS[worst]}  (defines common start)')

    hist_path = save_histogram(coverage_all, saved, effective_years, out_dir)

    # ── Ticker lists (print + .txt file) ─────────────────────────────────────
    downloaded_lines = [f'  {t:<6} {saved[t]:.1f}y  {ALL_TICKERS[t]}' for t in saved]
    skipped_lines    = [f'  {t:<6} {ALL_TICKERS[t]}' for t in skipped]

    print(f'\n{"─" * 60}')
    print(f'DOWNLOADED ({len(saved)}):')
    print('\n'.join(downloaded_lines) or '  (none)')
    print(f'\nSKIPPED ({len(skipped)}):')
    print('\n'.join(skipped_lines) or '  (none)')
    print(f'{"─" * 60}')

    txt_path = os.path.join(out_dir, 'ticker_summary.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f'Common start date : {common_start.date()}\n')
        f.write(f'Effective coverage: {effective_years:.1f} years\n\n')
        f.write(f'DOWNLOADED ({len(saved)}):\n')
        f.write('\n'.join(downloaded_lines) or '  (none)')
        f.write(f'\n\nSKIPPED ({len(skipped)}):\n')
        f.write('\n'.join(skipped_lines) or '  (none)')
        f.write('\n')

    print(f'\nHistogram    : {hist_path}')
    print(f'Ticker list  : {txt_path}')
    print(f'Data dir     : {out_dir}')
    print(sep)


if __name__ == '__main__':
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.join(script_dir, 'input_data')

    p = argparse.ArgumentParser(description='Download Xetra ETF historical data via IBKR TWS.')
    p.add_argument('--out-dir', '-o', default=default_out,
                   help=f'Output directory (default: {default_out})')
    args = p.parse_args()
    run(args.out_dir)
