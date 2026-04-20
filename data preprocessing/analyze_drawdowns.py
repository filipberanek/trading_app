import os
import sys
from statistics import mean, stdev

try:
    import pandas as pd
except Exception:
    print('pandas is required. Install it with: pip install pandas')
    sys.exit(1)


def detect_peaks_troughs(dates, prices):
    n = len(prices)
    if n == 0:
        return []

    # find initial trend
    trend = None
    for i in range(1, n):
        if prices[i] > prices[i - 1]:
            trend = 'up'
            break
        if prices[i] < prices[i - 1]:
            trend = 'down'
            break

    if trend is None:
        return []

    last_max = prices[0]
    last_max_idx = 0
    last_min = prices[0]
    last_min_idx = 0

    peaks = []
    troughs = []

    for i in range(1, n):
        p = prices[i]
        if trend == 'up':
            if p >= last_max:
                last_max = p
                last_max_idx = i
            if p < prices[i - 1]:
                # up -> down: record peak
                peaks.append((last_max_idx, last_max, dates[last_max_idx]))
                trend = 'down'
                last_min = p
                last_min_idx = i
        else:  # trend == 'down'
            if p <= last_min:
                last_min = p
                last_min_idx = i
            if p > prices[i - 1]:
                # down -> up: record trough
                troughs.append((last_min_idx, last_min, dates[last_min_idx]))
                trend = 'up'
                last_max = p
                last_max_idx = i

    return peaks, troughs


def pair_peaks_troughs(peaks, troughs):
    # pair in time-order: each peak paired with the next trough that occurs after it
    pairs = []
    ti = 0
    for pk_idx, pk_val, pk_date in peaks:
        # find first trough with index > pk_idx
        while ti < len(troughs) and troughs[ti][0] <= pk_idx:
            ti += 1
        if ti < len(troughs):
            tr_idx, tr_val, tr_date = troughs[ti]
            pairs.append({
                'peak_idx': pk_idx,
                'peak_val': pk_val,
                'peak_date': pk_date,
                'trough_idx': tr_idx,
                'trough_val': tr_val,
                'trough_date': tr_date,
            })
            ti += 1

    return pairs


def analyze_drawdowns(path_csv):
    df = pd.read_csv(path_csv, parse_dates=['Date'])
    if 'Close' not in df.columns:
        print('CSV must contain a Close column')
        return 1

    dates = df['Date'].tolist()
    prices = df['Close'].astype(float).tolist()

    peaks, troughs = detect_peaks_troughs(dates, prices)
    pairs = pair_peaks_troughs(peaks, troughs)

    drawdowns_abs = []
    drawdowns_pct = []
    rows = []

    for pair in pairs:
        pk = pair['peak_val']
        tr = pair['trough_val']
        dd = pk - tr
        dd_pct = dd / pk if pk != 0 else 0.0
        drawdowns_abs.append(dd)
        drawdowns_pct.append(dd_pct)
        rows.append({
            'peak_date': pair['peak_date'],
            'peak_val': pk,
            'trough_date': pair['trough_date'],
            'trough_val': tr,
            'drawdown_abs': dd,
            'drawdown_pct': dd_pct,
        })

    if len(drawdowns_abs) == 0:
        print('No peak->trough pairs found.')
        return 0

    summary = {
        'count': len(drawdowns_abs),
        'mean_abs': mean(drawdowns_abs),
        'std_abs': stdev(drawdowns_abs) if len(drawdowns_abs) > 1 else 0.0,
        'max_abs': max(drawdowns_abs),
        'mean_pct': mean(drawdowns_pct),
        'std_pct': stdev(drawdowns_pct) if len(drawdowns_pct) > 1 else 0.0,
        'max_pct': max(drawdowns_pct),
    }

    out_df = pd.DataFrame(rows)
    out_csv = os.path.join(os.path.dirname(path_csv), 'drawdowns_detail.csv')
    out_df.to_csv(out_csv, index=False)

    print('Drawdowns summary:')
    print(f"Count: {summary['count']}")
    print(f"Mean abs: {summary['mean_abs']:.6f}")
    print(f"Std abs: {summary['std_abs']:.6f}")
    print(f"Max abs: {summary['max_abs']:.6f}")
    print(f"Mean pct: {summary['mean_pct']:.6%}")
    print(f"Std pct: {summary['std_pct']:.6%}")
    print(f"Max pct: {summary['max_pct']:.6%}")
    print(f'Detailed per-drawdown csv written to: {out_csv}')

    return 0


if __name__ == '__main__':
    # default path is the data file in the sibling 'data' folder
    base_dir = os.path.dirname(__file__)
    default_csv = os.path.join(base_dir, 'data', 'ndx_20260419T190718Z.csv')
    path = sys.argv[1] if len(sys.argv) > 1 else default_csv
    sys.exit(analyze_drawdowns(path))
