"""
Compute pairwise correlation matrix of daily returns for all tickers in input_data/.

Output
------
  Print  : formatted correlation matrix + strongest/weakest pairs
  File   : analysis_outputs/correlation_matrix.txt
"""
from __future__ import annotations

import os
import sys

try:
    import pandas as pd
except Exception:
    print('pandas is required.  pip install pandas')
    sys.exit(1)


# ── Load all tickers ──────────────────────────────────────────────────────────

def _load_returns(input_dir: str) -> pd.DataFrame:
    """Load Close prices for all CSVs, align on common dates, return daily log-returns."""
    frames = {}
    for fname in sorted(os.listdir(input_dir)):
        if not fname.endswith('.csv'):
            continue
        ticker = os.path.splitext(fname)[0]
        try:
            df = pd.read_csv(
                os.path.join(input_dir, fname),
                parse_dates=['Date'],
                index_col='Date',
                usecols=['Date', 'Close'],
            )
            frames[ticker] = df['Close'].astype(float)
        except Exception as e:
            print(f'  SKIP {fname}: {e}')

    if not frames:
        return pd.DataFrame()

    prices  = pd.DataFrame(frames).sort_index()
    # inner-join: only days where ALL tickers have data
    prices  = prices.dropna(how='any')
    returns = prices.pct_change().dropna()
    return returns


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_matrix(corr: pd.DataFrame) -> list[str]:
    tickers = list(corr.columns)
    col_w   = 7
    lbl_w   = max(len(t) for t in tickers)

    header = ' ' * lbl_w + '  ' + '  '.join(f'{t:>{col_w}}' for t in tickers)
    sep    = '-' * len(header)
    lines  = [header, sep]

    for row_t in tickers:
        cells = []
        for col_t in tickers:
            v = corr.loc[row_t, col_t]
            if row_t == col_t:
                cells.append(f"{'1.00':>{col_w}}")
            else:
                cells.append(f'{v:>{col_w}.2f}')
        lines.append(f'{row_t:<{lbl_w}}  ' + '  '.join(cells))

    return lines


def _top_pairs(corr: pd.DataFrame, n: int = 10) -> tuple[list, list]:
    tickers = list(corr.columns)
    pairs = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            pairs.append((corr.loc[a, b], a, b))

    pairs.sort(key=lambda x: x[0], reverse=True)
    return pairs[:n], pairs[-n:][::-1]


def _build_report(returns: pd.DataFrame) -> str:
    corr    = returns.corr()
    tickers = list(corr.columns)
    n       = len(tickers)
    start   = returns.index[0].date()
    end     = returns.index[-1].date()
    days    = len(returns)

    lines = [
        f"Correlation matrix — daily returns ({n} tickers)",
        f"Period: {start} to {end}  ({days} trading days, inner-join alignment)",
        '',
    ]
    lines += _fmt_matrix(corr)

    top, bot = _top_pairs(corr, n=min(10, n * (n - 1) // 4))

    lines += [
        '',
        f"Top {len(top)} most correlated pairs:",
    ]
    for v, a, b in top:
        lines.append(f"  {a:<6} <-> {b:<6}  {v:+.3f}")

    lines += [
        '',
        f"Top {len(bot)} least correlated pairs:",
    ]
    for v, a, b in bot:
        lines.append(f"  {a:<6} <-> {b:<6}  {v:+.3f}")

    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(input_dir: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)

    print(f'Loading tickers from {input_dir} ...')
    returns = _load_returns(input_dir)

    if returns.empty:
        print('No data loaded.')
        return

    print(f'Loaded {returns.shape[1]} tickers, {len(returns)} common trading days.\n')

    report = _build_report(returns)
    print(report)

    txt_path = os.path.join(out_dir, 'correlation_matrix.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(report + '\n')
    print(f'\nSaved: {txt_path}')


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir  = os.path.join(script_dir, 'input_data')
    out_dir    = os.path.join(script_dir, 'analysis_outputs')
    run(input_dir, out_dir)
