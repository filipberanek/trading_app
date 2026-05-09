"""
Backtest - Multi-Asset Rotation (Antonacci Dual Momentum)

Each day compute N-day momentum for risky assets and a cash safe haven.

Selection rules:
  1. Relative momentum: find risky asset with highest N-day return.
  2. Absolute momentum: if the best risky asset has negative momentum → hold CASH instead.

Signal checked daily. Trade at next open when the selected asset changes.

This is Antonacci's Dual Momentum correctly implemented:
- In bear markets momentum turns negative → rotates toward safer assets
- If all risky assets have negative momentum → CASH (zero-risk, zero-return)

Grid search: lookback window (21-252 days)
"""

import os
import sys
import itertools
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

_ALGO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ALGO_ROOT not in sys.path:
    sys.path.insert(0, _ALGO_ROOT)
from data_loader import load_all


DEFAULT_RISKY  = ('QQQ', 'TLT', 'GLD')
DEFAULT_SAFE   = 'XEON'

TICKER_NAMES: dict = {
    'EQQQ': 'Invesco NASDAQ-100', 'QQQ':  'Invesco NASDAQ-100',
    'IUES': 'S&P 500 Energy',     'IGLN': 'Physical Gold',
    'IDTL': 'Treasury 20+yr',     'IBTM': 'Treasury 7-10yr',
    'IBZL': 'MSCI Brazil',        'EEA':  'MSCI E.Europe',
    'IUCS': 'S&P 500 Cons.Stpls', 'SEGA': 'Euro Agg Bond',
    'TLT':  'iSh 20+yr Treasury', 'GLD':  'SPDR Gold',
    'SHY':  'iSh 1-3yr Treasury', 'CASH': 'Cash (risk-off)',
    'XEON': 'EUR Overnight (XEON)',
}


def _ticker_label(t: str) -> str:
    return f'{t} — {TICKER_NAMES[t]}' if t in TICKER_NAMES else t


def fetch_all(assets, period='5y'):
    """Load Open+Close for each asset. Returns dict {ticker: df}. CASH is skipped."""
    tradeable = [a for a in assets if a != 'CASH']
    return load_all(tradeable, period=period)


def align_assets(dfs, assets):
    """Inner-join Close and Open DataFrames across all tradeable assets. CASH is excluded."""
    tradeable = [a for a in assets if a != 'CASH']
    closes = pd.DataFrame({t: dfs[t]['Close'] for t in tradeable}).dropna()
    opens  = pd.DataFrame({t: dfs[t]['Open']  for t in tradeable}).dropna()
    return closes, opens


def select_asset(mom_row, risky_assets, safe_asset):
    """
    Relative + absolute momentum selection:
    - Pick risky asset with highest momentum.
    - If that momentum <= 0, fall back to safe_asset.
    """
    risky_mom = {t: float(mom_row[t]) for t in risky_assets if not pd.isna(mom_row[t])}
    if not risky_mom:
        return safe_asset
    best = max(risky_mom, key=risky_mom.get)
    return best if risky_mom[best] > 0 else safe_asset


def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def compute_stats(equity_series, initial_capital, closed_trades, bh_close=None):
    trades_df = pd.DataFrame(closed_trades)
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    if bh_close is not None and years > 0:
        bh_cagr = (float(bh_close.iloc[-1]) / float(bh_close.iloc[0])) ** (1 / years) - 1
    else:
        bh_cagr = np.nan
    md = max_drawdown(equity_series)
    if len(trades_df) > 0 and 'pnl' in trades_df.columns:
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df)
        avg_pnl = trades_df['pnl'].mean()
        trade_returns = (trades_df['exit_price'] - trades_df['entry_price']) / trades_df['entry_price']
        avg_trade_return = trade_returns.mean()
        max_trade_gain = trade_returns.max()
        max_trade_drop = trade_returns.min()
    else:
        win_rate = avg_pnl = avg_trade_return = max_trade_gain = max_trade_drop = np.nan
    return {
        'total_return': total_return, 'cagr': cagr, 'bh_cagr': bh_cagr,
        'max_drawdown': md, 'n_trades_closed': len(trades_df),
        'win_rate': win_rate, 'avg_pnl': avg_pnl,
        'avg_trade_return': avg_trade_return,
        'max_trade_gain': max_trade_gain, 'max_trade_drop': max_trade_drop,
        'trades_df': trades_df,
    }


def print_stats(stats, initial_capital, equity_series, lookback, risky_assets, safe_asset, out_paths):
    print('Multi-Asset Rotation backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'Lookback window:          {lookback} days')
    print(f'Risky assets:             {list(risky_assets)}')
    print(f'Safe asset:               {safe_asset}')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    print(f'CAGR QQQ buy&hold:        {stats["bh_cagr"]:.2%}' if not pd.isna(stats['bh_cagr']) else 'CAGR QQQ buy&hold:        N/A')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Number of rotations:      {stats["n_trades_closed"]}')
    if not pd.isna(stats['win_rate']):
        print(f'Win rate:                 {stats["win_rate"]:.2%}')
        print(f'Average return per hold:  {stats["avg_trade_return"]:.2%}')
        print(f'Max gain per hold:        {stats["max_trade_gain"]:.2%}')
        print(f'Max drop per hold:        {stats["max_trade_drop"]:.2%}')
    print(f'Rotations CSV:            {out_paths["trades_csv"]}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots(closes, equity_series, held_asset_list, stats, lookback, risky_assets, out_dir):
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date']  = pd.to_datetime(trades_df['exit_date'])

    colors = {'QQQ': 'tab:blue', 'TLT': 'tab:orange', 'GLD': 'tab:green', 'CASH': 'gray'}

    fig, (ax_price, ax_equity, ax_held) = plt.subplots(
        3, 1, sharex=True, figsize=(14, 12),
        gridspec_kw={'height_ratios': [3, 2, 1]}
    )

    # CASH has no price data — only plot tradeable assets
    for t in risky_assets:
        if t in closes.columns:
            norm = closes[t] / float(closes[t].iloc[0])
            norm.plot(ax=ax_price, label=_ticker_label(t), color=colors.get(t), linewidth=1.2)
    ax_price.set_title(f'Multi-Asset Rotation — lookback {lookback} days')
    ax_price.set_ylabel('Normalized price (base=1)')
    ax_price.legend()
    ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    # Held chart includes CASH as a valid state
    all_states = list(risky_assets) + ['CASH']
    held_series = pd.Series(held_asset_list, index=equity_series.index)
    asset_codes = {a: i for i, a in enumerate(all_states)}
    held_numeric = held_series.map(asset_codes).fillna(-1)
    held_numeric.plot(ax=ax_held, drawstyle='steps-post', color='purple', linewidth=1)
    ax_held.set_yticks(list(asset_codes.values()))
    ax_held.set_yticklabels(list(asset_codes.keys()), fontsize=8)
    ax_held.set_ylabel('Held asset')
    ax_held.grid(True)

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_multi_asset.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


def run_backtest_multi_asset(period='5y', initial_capital=10000.0,
                              lookback=126,
                              risky_assets=DEFAULT_RISKY,
                              safe_asset=DEFAULT_SAFE,
                              verbose=True, dfs=None):
    out_dir = os.path.dirname(__file__)

    all_assets = list(risky_assets) + ([safe_asset] if safe_asset != 'CASH' else [])

    if dfs is None:
        print('Downloading asset data...')
        dfs = fetch_all(all_assets, period)

    closes, opens = align_assets(dfs, all_assets)
    if closes.empty:
        raise ValueError('No overlapping trading days across assets.')

    momentum = closes / closes.shift(lookback) - 1

    cash = float(initial_capital)
    shares = 0.0
    current_asset = None
    entry_price = None
    entry_date  = None
    entry_idx   = None

    equity_list    = []
    equity_dates   = []
    held_asset_list = []
    closed_trades  = []

    for i in range(len(closes)):
        date  = closes.index[i]
        price = float(closes[current_asset].iat[i]) if current_asset and current_asset != 'CASH' else 0.0

        eq = cash + shares * price
        equity_list.append(eq)
        equity_dates.append(date)
        held_asset_list.append(current_asset or safe_asset)

        if i < lookback or momentum.iloc[i].isna().all():
            continue

        target = select_asset(momentum.iloc[i], risky_assets, safe_asset)

        if target != current_asset and i + 1 < len(closes):
            next_date = closes.index[i + 1]

            # Close current position
            if current_asset is not None and current_asset != 'CASH' and shares > 0:
                exit_px = float(opens[current_asset].iat[i + 1])
                proceeds = shares * exit_px
                pnl = proceeds - shares * entry_price
                closed_trades.append({
                    'asset': current_asset,
                    'entry_date': entry_date, 'entry_price': entry_price,
                    'exit_date': next_date,   'exit_price': exit_px,
                    'shares': shares, 'pnl': pnl, 'held_days': i + 1 - entry_idx,
                })
                cash = proceeds
                shares = 0.0

            if target != 'CASH':
                buy_px = float(opens[target].iat[i + 1])
                shares = cash / buy_px
                cash  -= shares * buy_px
                entry_price = buy_px
            else:
                entry_price = None

            current_asset = target
            entry_date    = next_date
            entry_idx     = i + 1

    equity_series = pd.Series(equity_list, index=equity_dates)
    bh_col = next((c for c in ('EQQQ', 'QQQ') if c in closes.columns), None)
    bh_close = closes[bh_col] if bh_col else None
    stats = compute_stats(equity_series, initial_capital, closed_trades, bh_close=bh_close)

    trades_csv = fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_multi_asset.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots(closes, equity_series, held_asset_list, stats,
                               lookback, risky_assets, out_dir)
        print_stats(stats, initial_capital, equity_series, lookback, risky_assets, safe_asset,
                    {'trades_csv': trades_csv, 'fig_path': fig_path})

    def _f(v):
        return round(float(v), 3) if not pd.isna(v) else None

    return {
        'initial_capital': float(initial_capital),
        'final_equity': _f(equity_series.iloc[-1]),
        'total_return': _f(stats['total_return']),
        'cagr': _f(stats['cagr']),
        'bh_cagr': _f(stats['bh_cagr']),
        'max_drawdown': _f(stats['max_drawdown']),
        'n_trades_closed': int(stats['n_trades_closed']),
        'win_rate': _f(stats['win_rate']),
        'avg_trade_return': _f(stats['avg_trade_return']),
        'max_trade_gain': _f(stats['max_trade_gain']),
        'max_trade_drop': _f(stats['max_trade_drop']),
        'fig_path': fig_path,
        'trades_csv': trades_csv,
    }


def grid_search(period='5y', initial_capital=10000.0,
                lookback_values=(21, 42, 63, 126, 189, 252),
                risky_assets=DEFAULT_RISKY,
                safe_asset=DEFAULT_SAFE,
                maximize='cagr'):
    print(f'Grid search: {len(lookback_values)} combinations...')
    print('Downloading all asset data once...')
    dfs = fetch_all(list(risky_assets), period)

    results = []
    for lb in lookback_values:
        try:
            res = run_backtest_multi_asset(
                period=period, initial_capital=initial_capital,
                lookback=lb, risky_assets=risky_assets, safe_asset=safe_asset,
                verbose=False, dfs=dfs,
            )
            results.append({
                'lookback': lb,
                'cagr': res['cagr'], 'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'], 'win_rate': res['win_rate'],
                'n_trades': res['n_trades_closed'],
            })
        except Exception as e:
            print(f'  ERROR lookback={lb}: {e}')

    results_df = pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)
    print(f'\nAll results by {maximize}:')
    print(results_df.to_string(index=False))

    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nFull results saved to: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best parameters (by {maximize}) ---')
    print(f'  lookback={int(best["lookback"])} days')
    print('Running full backtest with best parameters...\n')
    run_backtest_multi_asset(
        period=period, initial_capital=initial_capital,
        lookback=int(best['lookback']),
        risky_assets=risky_assets, safe_asset=safe_asset,
        verbose=True, dfs=dfs,
    )
    return results_df


if __name__ == '__main__':
    res = run_backtest_multi_asset(initial_capital=10000.0, lookback=126)
    print('\nRESULT:', res)
