"""
Analyze peak-to-trough drawdowns for every CSV in input_data/.

Output
------
  Print  : per-ticker table + overall ranking
  File   : analysis_outputs/drawdown_summary.txt
"""
from __future__ import annotations

import os
import sys
from statistics import mean, stdev

try:
    import pandas as pd
except Exception:
    print('pandas is required.  pip install pandas')
    sys.exit(1)


# ── Peak / trough detection ───────────────────────────────────────────────────

def _detect_peaks_troughs(dates: list, prices: list):
    n = len(prices)
    trend = None
    for i in range(1, n):
        if prices[i] > prices[i - 1]:
            trend = 'up'
            break
        if prices[i] < prices[i - 1]:
            trend = 'down'
            break
    if trend is None:
        return [], []

    last_max, last_max_idx = prices[0], 0
    last_min, last_min_idx = prices[0], 0
    peaks, troughs = [], []

    for i in range(1, n):
        p = prices[i]
        if trend == 'up':
            if p >= last_max:
                last_max, last_max_idx = p, i
            if p < prices[i - 1]:
                peaks.append((last_max_idx, last_max, dates[last_max_idx]))
                trend = 'down'
                last_min, last_min_idx = p, i
        else:
            if p <= last_min:
                last_min, last_min_idx = p, i
            if p > prices[i - 1]:
                troughs.append((last_min_idx, last_min, dates[last_min_idx]))
                trend = 'up'
                last_max, last_max_idx = p, i

    return peaks, troughs


def _pair_peaks_troughs(peaks: list, troughs: list) -> list[dict]:
    pairs, ti = [], 0
    for pk_idx, pk_val, pk_date in peaks:
        while ti < len(troughs) and troughs[ti][0] <= pk_idx:
            ti += 1
        if ti < len(troughs):
            _, tr_val, tr_date = troughs[ti]
            pairs.append(dict(
                peak_date=pk_date, peak_val=pk_val,
                trough_date=tr_date, trough_val=tr_val,
            ))
            ti += 1
    return pairs


# ── Per-ticker analysis ───────────────────────────────────────────────────────

def _analyze_one(csv_path: str) -> dict | None:
    """Return summary dict for one ticker CSV, or None on error."""
    try:
        df = pd.read_csv(csv_path, parse_dates=['Date'])
    except Exception as e:
        print(f'  ERROR reading {csv_path}: {e}')
        return None

    if 'Close' not in df.columns or df.empty:
        print(f'  SKIP {os.path.basename(csv_path)}: no Close column or empty')
        return None

    dates  = df['Date'].tolist()
    prices = df['Close'].astype(float).tolist()

    peaks, troughs = _detect_peaks_troughs(dates, prices)
    pairs          = _pair_peaks_troughs(peaks, troughs)

    if not pairs:
        return None

    pcts = [(p['peak_val'] - p['trough_val']) / p['peak_val']
            for p in pairs if p['peak_val'] != 0]
    if not pcts:
        return None

    ticker = os.path.splitext(os.path.basename(csv_path))[0]
    start  = df['Date'].iloc[0].date()
    end    = df['Date'].iloc[-1].date()

    return dict(
        ticker     = ticker,
        start      = start,
        end        = end,
        rows       = len(df),
        count      = len(pcts),
        mean_pct   = mean(pcts),
        std_pct    = stdev(pcts) if len(pcts) > 1 else 0.0,
        max_pct    = max(pcts),
        median_pct = sorted(pcts)[len(pcts) // 2],
    )


# ── Formatting helpers ────────────────────────────────────────────────────────

_HDR = (
    f"{'Ticker':<6}  {'Start':>10}  {'End':>10}  {'Bars':>5}  "
    f"{'DD#':>4}  {'MaxDD':>7}  {'MeanDD':>7}  {'MedianDD':>9}  {'StdDD':>7}"
)
_SEP = '-' * len(_HDR)


def _row(s: dict) -> str:
    return (
        f"{s['ticker']:<6}  {str(s['start']):>10}  {str(s['end']):>10}  "
        f"{s['rows']:>5}  {s['count']:>4}  "
        f"{s['max_pct']:>6.1%}  {s['mean_pct']:>6.1%}  "
        f"{s['median_pct']:>8.1%}  {s['std_pct']:>6.1%}"
    )


def _build_report(summaries: list[dict]) -> str:
    by_max = sorted(summaries, key=lambda x: x['max_pct'], reverse=True)
    lines  = [
        f"Drawdown analysis — {len(summaries)} tickers",
        f"Ranked by Max Drawdown (descending)",
        _SEP, _HDR, _SEP,
    ]
    lines += [_row(s) for s in by_max]
    lines.append(_SEP)

    # overall stats
    all_max  = [s['max_pct']  for s in summaries]
    all_mean = [s['mean_pct'] for s in summaries]
    lines += [
        '',
        f"Cross-ticker stats (worst MaxDD first):",
        f"  Avg  MaxDD across tickers : {mean(all_max):.1%}",
        f"  Avg MeanDD across tickers : {mean(all_mean):.1%}",
        f"  Ticker with largest MaxDD : {by_max[0]['ticker']}  ({by_max[0]['max_pct']:.1%})",
        f"  Ticker with smallest MaxDD: {by_max[-1]['ticker']}  ({by_max[-1]['max_pct']:.1%})",
    ]
    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(input_dir: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)

    csv_files = sorted(
        f for f in os.listdir(input_dir)
        if f.endswith('.csv')
    )

    if not csv_files:
        print(f'No CSV files found in {input_dir}')
        return

    print(f'Analyzing {len(csv_files)} files in {input_dir} ...\n')

    summaries = []
    for fname in csv_files:
        path = os.path.join(input_dir, fname)
        result = _analyze_one(path)
        if result:
            summaries.append(result)

    if not summaries:
        print('No drawdown data found.')
        return

    report = _build_report(summaries)
    print(report)

    txt_path = os.path.join(out_dir, 'drawdown_summary.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(report + '\n')
    print(f'\nSaved: {txt_path}')


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir  = os.path.join(script_dir, 'input_data')
    out_dir    = os.path.join(script_dir, 'analysis_outputs')
    run(input_dir, out_dir)
