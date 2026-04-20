"""Stáhne historická data pro index Nasdaq‑100 (ticker ^NDX) za celé dostupné období a uloží do složky `data`.

Požadavky: `yfinance`, `pandas` (nainstalujte `pip install yfinance pandas`)
"""
from __future__ import annotations
import os
import argparse
from datetime import datetime
import yfinance as yf


def download_ndx(out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    ticker = "^NDX"
    print(f"Downloading {ticker} history (max)...")
    t = yf.Ticker(ticker)
    df = t.history(period="max", interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError("No data downloaded for ^NDX")
    filename = os.path.join(out_dir, f"ndx_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv")
    df.to_csv(filename)
    return filename


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Download Nasdaq-100 (^NDX) historical data (max) and save as CSV.")
    default_out = os.path.join(os.path.dirname(__file__), "data")
    p.add_argument("--out-dir", "-o", default=default_out, help="Output directory (default: ./data)")
    args = p.parse_args()
    try:
        out = download_ndx(args.out_dir)
        print(f"Saved data to: {out}")
    except Exception as e:
        print(f"Error: {e}")
        raise
