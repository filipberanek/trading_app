"""
Select a subset of tickers that avoids high POSITIVE correlation.

Rule: a pair is "problematic" only when its correlation exceeds +threshold.
      Negative correlations are welcome (they aid diversification).

Two modes (can be combined):
  --n N            greedy: pick up to N tickers
  --threshold T    max allowed positive pairwise correlation (default 0.70)

Output
------
  Print  : greedy-selected set, sub-matrix, violation analysis, qualifying list
  File   : analysis_outputs/low_correlation_selection.txt
"""
from __future__ import annotations

import os
import sys
import argparse

try:
    import pandas as pd
except Exception:
    print('pandas is required.  pip install pandas')
    sys.exit(1)


# ── Load returns ──────────────────────────────────────────────────────────────

def _load_returns(input_dir: str) -> pd.DataFrame:
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

    prices  = pd.DataFrame(frames).sort_index().dropna(how='any')
    returns = prices.pct_change().dropna()
    return returns


# ── Greedy selection (positive-only threshold) ────────────────────────────────

SEED_TICKER = 'EQQQ'


def _greedy_select(corr: pd.DataFrame, n: int, threshold: float) -> list[str]:
    """
    Forward greedy selection.

    Seed  : always SEED_TICKER (EQQQ / Nasdaq-100).
    Step  : add the candidate with the lowest mean raw correlation to the
            already-selected set, provided no new pair exceeds +threshold.
    Stop  : when n tickers are selected or no candidate passes the threshold.
    """
    tickers = list(corr.columns)

    seed = SEED_TICKER if SEED_TICKER in tickers else tickers[0]
    selected  = [seed]
    remaining = [t for t in tickers if t != seed]

    while remaining and len(selected) < n:
        best_ticker = None
        best_score  = float('inf')

        for candidate in remaining:
            corrs_to_selected = [corr.loc[candidate, s] for s in selected]
            max_pos = max(corrs_to_selected)   # highest raw corr (threshold only on positive)

            if max_pos > threshold:
                continue  # this candidate would create a violating pair

            avg_corr = sum(corrs_to_selected) / len(corrs_to_selected)
            if avg_corr < best_score:
                best_score  = avg_corr
                best_ticker = candidate

        if best_ticker is None:
            break

        selected.append(best_ticker)
        remaining.remove(best_ticker)

    return selected


# ── Violation helpers ─────────────────────────────────────────────────────────

def _violating_pairs(corr: pd.DataFrame, tickers: list[str], threshold: float) -> list[tuple]:
    """All pairs within `tickers` whose correlation exceeds +threshold."""
    pairs = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            v = corr.loc[a, b]
            if v > threshold:
                pairs.append((v, a, b))
    return sorted(pairs, key=lambda x: x[0], reverse=True)


def _why_excluded(corr: pd.DataFrame, candidate: str,
                  selected: list[str], threshold: float) -> list[str]:
    """Which selected tickers block this candidate (corr > threshold)."""
    return [s for s in selected if corr.loc[candidate, s] > threshold]


# ── Formatting ────────────────────────────────────────────────────────────────

def _fmt_submatrix(corr: pd.DataFrame, selected: list[str], threshold: float) -> list[str]:
    sub   = corr.loc[selected, selected]
    col_w = 7
    lbl_w = max(len(t) for t in selected)

    header = ' ' * lbl_w + '  ' + '  '.join(f'{t:>{col_w}}' for t in selected)
    sep    = '-' * len(header)
    lines  = [header, sep]

    for row_t in selected:
        cells = []
        for col_t in selected:
            v = sub.loc[row_t, col_t]
            if row_t == col_t:
                cells.append(f"{'1.00':>{col_w}}")
            elif v > threshold:
                cells.append(f'{v:>{col_w}.2f}!')  # flag violating cells
            else:
                cells.append(f'{v:>{col_w}.2f}')
        lines.append(f'{row_t:<{lbl_w}}  ' + '  '.join(cells))

    return lines


def _build_report(
    returns: pd.DataFrame,
    selected: list[str],
    n: int,
    threshold: float,
) -> str:
    corr    = returns.corr()
    all_t   = list(corr.columns)
    excluded = [t for t in all_t if t not in selected]
    start   = returns.index[0].date()
    end     = returns.index[-1].date()
    days    = len(returns)

    all_pairs = [(corr.loc[a, b], a, b)
                 for i, a in enumerate(all_t) for b in all_t[i + 1:]]
    all_pairs.sort(key=lambda x: x[0])

    sel_pairs = [(corr.loc[a, b], a, b)
                 for i, a in enumerate(selected) for b in selected[i + 1:]]
    sel_pairs.sort(key=lambda x: x[0])

    violations_in_selection = _violating_pairs(corr, selected, threshold)

    mean_pos_vs_all = {
        t: corr.loc[t, [x for x in all_t if x != t]].clip(lower=0).mean()
        for t in selected
    }

    lines = [
        f"Low positive-correlation ticker selection",
        f"Universe  : {len(all_t)} tickers",
        f"Period    : {start} to {end}  ({days} trading days)",
        f"Threshold : positive corr > {threshold:.2f} is problematic  "
        f"(negative correlations are fine)",
        f"Target n  : {n}",
        '',
    ]

    # ── Section 1: selected set ───────────────────────────────────────────────
    lines += [f"{'─'*60}",
              f"SELECTED SET  ({len(selected)} tickers)",
              f"{'─'*60}"]
    for i, t in enumerate(selected, 1):
        lines.append(f"  {i:2}. {t:<6}  avg positive corr vs universe: {mean_pos_vs_all[t]:.3f}")

    lines += ['', 'Sub-matrix  (! = pair exceeds threshold):']
    lines += _fmt_submatrix(corr, selected, threshold)

    if sel_pairs:
        pair_vals = [v for v, _, _ in sel_pairs]
        lines += [
            '',
            f"  Pairs in selection : {len(sel_pairs)}",
            f"  Max positive corr  : {max(pair_vals):+.3f}",
            f"  Avg corr           : {sum(pair_vals)/len(pair_vals):+.3f}",
            f"  Min corr           : {min(pair_vals):+.3f}",
        ]

    if violations_in_selection:
        lines += ['', f"  WARNING — {len(violations_in_selection)} violating pair(s) in selection:"]
        for v, a, b in violations_in_selection:
            lines.append(f"    {a} <-> {b}  {v:+.3f}")
    else:
        lines.append(f"\n  All pairs within selection are below threshold. ✓")

    # ── Section 2: qualifying assets (all pairs in full universe) ─────────────
    lines += [
        '',
        f"{'─'*60}",
        f"ASSETS SATISFYING THE CONDITION",
        f"(no pair with ANY other ticker in universe exceeds +{threshold:.2f})",
        f"{'─'*60}",
    ]
    qualifying = []
    for t in all_t:
        others = [x for x in all_t if x != t]
        max_pos_corr = max(corr.loc[t, x] for x in others)
        if max_pos_corr <= threshold:
            qualifying.append((max_pos_corr, t))

    if qualifying:
        qualifying.sort(key=lambda x: x[0])
        for max_c, t in qualifying:
            lines.append(f"  {t:<6}  max positive corr with any other ticker: {max_c:+.3f}")
    else:
        lines.append(f"  None — every ticker has at least one pair above +{threshold:.2f}")

    # ── Section 3: excluded tickers and why ───────────────────────────────────
    if excluded:
        lines += [
            '',
            f"{'─'*60}",
            f"EXCLUDED FROM GREEDY SELECTION  ({len(excluded)} tickers)",
            f"{'─'*60}",
        ]
        for t in excluded:
            blockers = _why_excluded(corr, t, selected, threshold)
            if blockers:
                blocker_str = ', '.join(
                    f"{b} ({corr.loc[t, b]:+.2f})" for b in blockers
                )
                lines.append(f"  {t:<6}  blocked by: {blocker_str}")
            else:
                lines.append(f"  {t:<6}  dropped (n limit reached)")

    # ── Section 4: top/bottom pairs in full universe ──────────────────────────
    lines += [
        '',
        f"{'─'*60}",
        f"REFERENCE — ALL UNIVERSE PAIRS  (highest positive corr first)",
        f"{'─'*60}",
    ]
    sorted_desc = sorted(all_pairs, key=lambda x: x[0], reverse=True)
    for v, a, b in sorted_desc:
        flag = '  ← VIOLATION' if v > threshold else ''
        lines.append(f"  {a:<6} <-> {b:<6}  {v:+.3f}{flag}")

    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(input_dir: str, out_dir: str, n: int, threshold: float) -> None:
    os.makedirs(out_dir, exist_ok=True)

    print(f'Loading tickers from {input_dir} ...')
    returns = _load_returns(input_dir)

    if returns.empty:
        print('No data loaded.')
        return

    total = returns.shape[1]
    print(f'Loaded {total} tickers, {len(returns)} common trading days.\n')

    n    = min(n, total)
    corr = returns.corr()

    selected = _greedy_select(corr, n=n, threshold=threshold)
    report   = _build_report(returns, selected, n=n, threshold=threshold)

    print(report)

    txt_path = os.path.join(out_dir, 'low_correlation_selection.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(report + '\n')
    print(f'\nSaved: {txt_path}')


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir  = os.path.join(script_dir, 'input_data')
    out_dir    = os.path.join(script_dir, 'analysis_outputs')

    p = argparse.ArgumentParser(description='Select tickers by positive-correlation threshold.')
    p.add_argument('--n',         type=int,   default=8,
                   help='Max tickers to select (default: 8)')
    p.add_argument('--threshold', type=float, default=0.70,
                   help='Max allowed positive pairwise correlation (default: 0.70)')
    args = p.parse_args()

    run(input_dir, out_dir, n=args.n, threshold=args.threshold)
