"""
Backtest - Dual Momentum (Antonacci) — Single-asset & Multi-asset modes

Single-asset mode (dfs=None):
  QQQ N-day return > 0 → hold QQQ, else → cash.

Multi-asset mode (dfs provided, default):
  1. Relative momentum: pick risky asset with highest N-day return.
  2. Absolute momentum: if best risky asset momentum <= 0 → hold CASH instead.
  Signal checked daily. Trade at next open when selected asset changes.
  CASH earns zero return — no interest, no price movement.

Grid search: lookback window 21–252 days.
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

_ALGO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ALGO_ROOT not in sys.path:
    sys.path.insert(0, _ALGO_ROOT)
from data_loader import load_ohlcv, load_all

DEFAULT_RISKY = ('QQQ', 'TLT', 'GLD')
DEFAULT_SAFE  = 'XEON'

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


# ── data helpers ─────────────────────────────────────────────────────────────

def fetch_data(ticker='QQQ', period='5y'):
    return load_ohlcv(ticker, period=period)


def fetch_all(assets, period='5y'):
    tradeable = [a for a in assets if a != 'CASH']
    return load_all(tradeable, period=period)


def align_assets(dfs, assets):
    tradeable = [a for a in assets if a != 'CASH']
    closes = pd.DataFrame({t: dfs[t]['Close'] for t in tradeable}).dropna()
    opens  = pd.DataFrame({t: dfs[t]['Open']  for t in tradeable}).dropna()
    return closes, opens


# ── signal selection ─────────────────────────────────────────────────────────

def select_asset(mom_row, risky_assets, safe_asset):
    risky_mom = {t: float(mom_row[t]) for t in risky_assets if not pd.isna(mom_row[t])}
    if not risky_mom:
        return safe_asset
    best = max(risky_mom, key=risky_mom.get)
    return best if risky_mom[best] > 0 else safe_asset


# ── stats / output ────────────────────────────────────────────────────────────

def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def compute_stats(equity_series, initial_capital, closed_trades, bh_close=None):
    trades_df = pd.DataFrame(closed_trades)
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    bh_cagr = ((float(bh_close.iloc[-1]) / float(bh_close.iloc[0])) ** (1 / years) - 1
               if bh_close is not None and years > 0 else np.nan)
    md = max_drawdown(equity_series)
    if len(trades_df) > 0 and 'pnl' in trades_df.columns:
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df)
        avg_pnl = trades_df['pnl'].mean()
        tr = (trades_df['exit_price'] - trades_df['entry_price']) / trades_df['entry_price']
        avg_trade_return, max_trade_gain, max_trade_drop = tr.mean(), tr.max(), tr.min()
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


def print_stats(stats, initial_capital, equity_series, lookback, mode_label, out_paths):
    print(f'Dual Momentum ({mode_label}) backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'Lookback window:          {lookback} days')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    if not pd.isna(stats['bh_cagr']):
        print(f'CAGR QQQ buy&hold:        {stats["bh_cagr"]:.2%}')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Number of rotations:      {stats["n_trades_closed"]}')
    if not pd.isna(stats['win_rate']):
        print(f'Win rate:                 {stats["win_rate"]:.2%}')
        print(f'Average return per hold:  {stats["avg_trade_return"]:.2%}')
        print(f'Max gain per hold:        {stats["max_trade_gain"]:.2%}')
        print(f'Max drop per hold:        {stats["max_trade_drop"]:.2%}')
    print(f'Trades CSV:               {out_paths["trades_csv"]}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots_multi(closes, equity_series, held_list, momentum_df,
                     stats, lookback, risky_assets, out_dir):
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date']  = pd.to_datetime(trades_df['exit_date'])

    colors = {'QQQ': 'tab:blue', 'TLT': 'tab:orange', 'GLD': 'tab:green', 'CASH': 'gray'}

    fig, (ax_price, ax_equity, ax_held) = plt.subplots(
        3, 1, sharex=True, figsize=(14, 12),
        gridspec_kw={'height_ratios': [3, 2, 1]}
    )
    # CASH has no price data — only plot tradeable risky assets
    for t in risky_assets:
        if t in closes.columns:
            norm = closes[t] / float(closes[t].iloc[0])
            norm.plot(ax=ax_price, label=_ticker_label(t), color=colors.get(t), linewidth=1.2)
    ax_price.set_title(f'Dual Momentum Multi-Asset — lookback {lookback}d')
    ax_price.set_ylabel('Normalized price')
    ax_price.legend(); ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value'); ax_equity.grid(True)

    # Held chart includes CASH as a valid state
    all_states = list(risky_assets) + ['CASH']
    held_series = pd.Series(held_list, index=equity_series.index)
    codes = {a: i for i, a in enumerate(all_states)}
    held_series.map(codes).fillna(-1).plot(ax=ax_held, drawstyle='steps-post', color='purple')
    ax_held.set_yticks(list(codes.values()))
    ax_held.set_yticklabels(list(codes.keys()), fontsize=8)
    ax_held.set_ylabel('Held'); ax_held.grid(True)

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_dual_momentum.png')
    fig.savefig(out_fig); plt.close(fig)
    return out_fig


def save_plots_single(df, equity_series, invested_list, momentum_series, stats, lookback, out_dir):
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date']  = pd.to_datetime(trades_df['exit_date'])

    fig, (ax_price, ax_equity, ax_mom) = plt.subplots(
        3, 1, sharex=True, figsize=(14, 12),
        gridspec_kw={'height_ratios': [3, 2, 1]}
    )
    df['Close'].plot(ax=ax_price, label='Close')
    if len(trades_df) > 0:
        ax_price.scatter(trades_df['entry_date'], trades_df['entry_price'],
                         marker='^', color='green', label='Buy', zorder=5)
        ax_price.scatter(trades_df['exit_date'], trades_df['exit_price'],
                         marker='v', color='red', label='Sell', zorder=5)
    ax_price.set_title(f'Dual Momentum Single-Asset — lookback {lookback}d')
    ax_price.set_ylabel('Price'); ax_price.legend(); ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value'); ax_equity.grid(True)

    momentum_series.plot(ax=ax_mom, color='purple', label=f'{lookback}-day momentum')
    ax_mom.axhline(0, color='black', linewidth=0.8, linestyle='--')
    ax_mom.fill_between(momentum_series.index, momentum_series.values,
                        where=momentum_series.values > 0, alpha=0.3, color='green')
    ax_mom.fill_between(momentum_series.index, momentum_series.values,
                        where=momentum_series.values < 0, alpha=0.3, color='red')
    ax_mom.set_ylabel('Momentum'); ax_mom.grid(True); ax_mom.legend()

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_dual_momentum.png')
    fig.savefig(out_fig); plt.close(fig)
    return out_fig


# ── backtest core ─────────────────────────────────────────────────────────────

def run_backtest_dual_momentum(ticker='QQQ', period='5y', initial_capital=10000.0,
                                lookback=126,
                                risky_assets=DEFAULT_RISKY,
                                safe_asset=DEFAULT_SAFE,
                                verbose=True, df=None, dfs=None):
    """
    dfs=None  → single-asset mode: QQQ vs cash (original, uses df parameter).
    dfs=dict  → multi-asset mode: rotates QQQ/TLT/GLD/SHY.
    """
    out_dir = os.path.dirname(__file__)

    def _f(v):
        return round(float(v), 3) if not pd.isna(v) else None

    # ── MULTI-ASSET MODE ─────────────────────────────────────────────────────
    if dfs is not None:
        all_assets = list(risky_assets) + ([safe_asset] if safe_asset != 'CASH' else [])
        closes, opens = align_assets(dfs, all_assets)
        if closes.empty:
            raise ValueError('No overlapping trading days across assets.')

        momentum = closes / closes.shift(lookback) - 1
        bh_col   = next((c for c in ('EQQQ', 'QQQ') if c in closes.columns), None)
        bh_close = closes[bh_col] if bh_col else None

        cash = float(initial_capital)
        shares = 0.0
        current_asset = None
        entry_price = entry_date = entry_idx = None
        equity_list, held_list, closed_trades = [], [], []

        for i in range(len(closes)):
            date  = closes.index[i]
            # CASH holds no shares — equity equals cash balance only
            price = float(closes[current_asset].iat[i]) if current_asset and current_asset != 'CASH' else 0.0
            eq = cash + shares * price
            equity_list.append(eq)
            held_list.append(current_asset or 'CASH')

            if i < lookback or momentum.iloc[i].isna().all():
                continue

            target = select_asset(momentum.iloc[i], risky_assets, safe_asset)

            if target != current_asset and i + 1 < len(closes):
                next_date = closes.index[i + 1]
                # Close current position (only if in a real asset, not CASH)
                if current_asset is not None and current_asset != 'CASH' and shares > 0:
                    exit_px = float(opens[current_asset].iat[i + 1])
                    pnl = shares * exit_px - shares * entry_price
                    closed_trades.append({
                        'asset': current_asset,
                        'entry_date': entry_date, 'entry_price': entry_price,
                        'exit_date': next_date,   'exit_price': exit_px,
                        'shares': shares, 'pnl': pnl,
                        'held_days': i + 1 - entry_idx,
                    })
                    cash = shares * exit_px
                    shares = 0.0
                if target != 'CASH':
                    # Buy the risky target asset
                    buy_px = float(opens[target].iat[i + 1])
                    shares = cash / buy_px
                    cash  -= shares * buy_px
                    entry_price = buy_px
                else:
                    # Move to CASH: stay flat, no purchase, no interest
                    entry_price = None
                current_asset = target
                entry_date    = next_date
                entry_idx     = i + 1

        equity_series = pd.Series(equity_list, index=closes.index)
        stats = compute_stats(equity_series, initial_capital, closed_trades, bh_close=bh_close)

        trades_csv = fig_path = None
        if verbose:
            trades_csv = os.path.join(out_dir, 'trades_detail_dual_momentum.csv')
            stats['trades_df'].to_csv(trades_csv, index=False)
            fig_path = save_plots_multi(closes, equity_series, held_list, momentum,
                                        stats, lookback, risky_assets, out_dir)
            print_stats(stats, initial_capital, equity_series, lookback,
                        f'multi {list(risky_assets)}→{safe_asset}',
                        {'trades_csv': trades_csv, 'fig_path': fig_path})

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
            'fig_path': fig_path, 'trades_csv': trades_csv,
        }

    # ── SINGLE-ASSET MODE (backward compat) ──────────────────────────────────
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    df['momentum'] = df['Close'] / df['Close'].shift(lookback) - 1
    df['signal']   = (df['momentum'] > 0).astype(float)
    df.loc[df['momentum'].isna(), 'signal'] = np.nan

    cash = float(initial_capital)
    shares = 0.0
    in_position = False
    entry_price = entry_date = entry_idx = None
    prev_signal = np.nan
    equity_list, equity_dates, invested_list, closed_trades = [], [], [], []

    for i in range(len(df)):
        date  = df.index[i]
        close = float(df['Close'].iat[i])
        pos_value = shares * close
        eq = cash + pos_value
        equity_list.append(eq)
        equity_dates.append(date)
        invested_list.append(pos_value / eq if eq > 0 else 0.0)

        sig_raw = df['signal'].iat[i]
        if pd.isna(sig_raw):
            continue
        sig = int(sig_raw)

        if in_position and sig == 0 and prev_signal == 1:
            proceeds = shares * close
            closed_trades.append({
                'entry_date': entry_date, 'entry_price': entry_price,
                'exit_date': date, 'exit_price': close,
                'shares': shares, 'pnl': proceeds - shares * entry_price,
                'held_days': i - entry_idx,
            })
            cash += proceeds
            shares = 0.0
            in_position = False
            entry_price = entry_date = entry_idx = None

        if not in_position and sig == 1 and prev_signal != 1:
            if i + 1 < len(df):
                next_open = float(df['Open'].iat[i + 1])
                shares = cash / next_open
                cash -= shares * next_open
                in_position = True
                entry_price = next_open
                entry_date  = df.index[i + 1]
                entry_idx   = i + 1
        prev_signal = sig

    equity_series = pd.Series(equity_list, index=equity_dates)
    stats = compute_stats(equity_series, initial_capital, closed_trades,
                          bh_close=df['Close'])

    trades_csv = fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_dual_momentum.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots_single(df, equity_series, invested_list,
                                     df['momentum'].reindex(equity_series.index),
                                     stats, lookback, out_dir)
        print_stats(stats, initial_capital, equity_series, lookback, 'QQQ vs cash',
                    {'trades_csv': trades_csv, 'fig_path': fig_path})

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
        'fig_path': fig_path, 'trades_csv': trades_csv,
    }


# ── grid search ───────────────────────────────────────────────────────────────

def grid_search(ticker='QQQ', period='5y', initial_capital=10000.0,
                lookback_values=(21, 42, 63, 126, 189, 252),
                risky_assets=DEFAULT_RISKY,
                safe_asset=DEFAULT_SAFE,
                maximize='cagr'):
    print(f'Grid search: {len(lookback_values)} combinations...')
    print(f'Downloading {list(risky_assets)} data once...')
    raw_dfs = fetch_all(list(risky_assets), period)

    results = []
    for lb in lookback_values:
        try:
            res = run_backtest_dual_momentum(
                initial_capital=initial_capital, lookback=lb,
                risky_assets=risky_assets, safe_asset=safe_asset,
                verbose=False, dfs=raw_dfs,
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
    print(f'  lookback={int(best["lookback"])} days, assets={list(risky_assets)}→{safe_asset}')
    print('Running full backtest with best parameters...\n')
    run_backtest_dual_momentum(
        initial_capital=initial_capital, lookback=int(best['lookback']),
        risky_assets=risky_assets, safe_asset=safe_asset,
        verbose=True, dfs=raw_dfs,
    )
    return results_df


if __name__ == '__main__':
    res = run_backtest_dual_momentum(initial_capital=10000.0, lookback=126)
    print('\nRESULT:', res)
