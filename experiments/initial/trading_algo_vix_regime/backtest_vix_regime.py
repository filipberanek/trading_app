"""
Backtest QQQ - VIX Regime Detection

Uses CBOE VIX (^VIX) as a market fear gauge to size exposure:
  VIX < vix_low  → 100% invested in QQQ  (calm market)
  VIX > vix_high → 0% cash               (fear/panic)
  Between        → 50% invested           (neutral zone)

Signal evaluated daily. When regime changes, trade at next open.
VIX data downloaded from yfinance as ^VIX.

Grid search: vix_low (15-25), vix_high (25-40)
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

_ALGO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ALGO_ROOT not in sys.path:
    sys.path.insert(0, _ALGO_ROOT)
from data_loader import load_ohlcv, load_vix


def fetch_data(ticker='QQQ', period='5y'):
    return load_ohlcv(ticker, period=period)


def fetch_vix(period='5y'):
    return load_vix(period=period)


def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def compute_stats(equity_series, initial_capital, closed_trades, df=None):
    trades_df = pd.DataFrame(closed_trades)
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    if df is not None and years > 0:
        bh_cagr = (float(df['Close'].iloc[-1]) / float(df['Close'].iloc[0])) ** (1 / years) - 1
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


def print_stats(stats, initial_capital, equity_series, vix_low, vix_high, out_paths):
    print('VIX Regime Detection backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'VIX low threshold:        {vix_low}')
    print(f'VIX high threshold:       {vix_high}')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    print(f'CAGR buy & hold:          {stats["bh_cagr"]:.2%}' if not pd.isna(stats['bh_cagr']) else 'CAGR buy & hold:          N/A')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Number of trades:         {stats["n_trades_closed"]}')
    if not pd.isna(stats['win_rate']):
        print(f'Win rate:                 {stats["win_rate"]:.2%}')
        print(f'Average return per trade: {stats["avg_trade_return"]:.2%}')
        print(f'Max gain per trade:       {stats["max_trade_gain"]:.2%}')
        print(f'Max drop per trade:       {stats["max_trade_drop"]:.2%}')
    print(f'Trades CSV:               {out_paths["trades_csv"]}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots(df, equity_series, invested_list, vix_series, stats, vix_low, vix_high, out_dir):
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])

    invested_series = pd.Series(invested_list, index=equity_series.index)

    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(14, 14),
                              gridspec_kw={'height_ratios': [3, 2, 1, 1]})
    ax_price, ax_equity, ax_inv, ax_vix = axes

    df['Close'].plot(ax=ax_price, label='Close')
    if len(trades_df) > 0:
        ax_price.scatter(trades_df['entry_date'], trades_df['entry_price'],
                         marker='^', color='green', label='Buy', zorder=5)
        ax_price.scatter(trades_df['exit_date'], trades_df['exit_price'],
                         marker='v', color='red', label='Sell', zorder=5)
    ax_price.set_title(f'VIX Regime Detection (low={vix_low}, high={vix_high})')
    ax_price.set_ylabel('Price')
    ax_price.legend()
    ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    ax_inv.fill_between(invested_series.index, invested_series.values * 100,
                        step='post', alpha=0.4, color='steelblue', label='Invested %')
    ax_inv.set_ylabel('Invested %')
    ax_inv.set_ylim(0, 105)
    ax_inv.grid(True)
    ax_inv.legend()

    vix_series.plot(ax=ax_vix, color='darkorange', label='VIX')
    ax_vix.axhline(vix_low, color='green', linestyle='--', linewidth=1, label=f'Low={vix_low}')
    ax_vix.axhline(vix_high, color='red', linestyle='--', linewidth=1, label=f'High={vix_high}')
    ax_vix.fill_between(vix_series.index, vix_series.values, vix_high,
                        where=vix_series.values > vix_high, alpha=0.2, color='red')
    ax_vix.set_ylabel('VIX')
    ax_vix.grid(True)
    ax_vix.legend()

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_vix_regime.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


def run_backtest_vix_regime(ticker='QQQ', period='5y', initial_capital=10000.0,
                             vix_low=20, vix_high=30,
                             verbose=True, df=None, vix_df=None):
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No QQQ data returned.')
    df = df.copy()

    if vix_df is None:
        vix_df = fetch_vix(period)
        vix_df.index = pd.to_datetime(vix_df.index)
    vix_df = vix_df.copy()

    combined = df.join(vix_df, how='inner')
    if combined.empty:
        raise ValueError('No overlapping dates between QQQ and VIX data.')
    df = combined[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    vix_aligned = combined['VIX']

    def target_alloc(vix_val):
        if vix_val < vix_low:
            return 1.0
        elif vix_val > vix_high:
            return 0.0
        return 0.5

    cash = float(initial_capital)
    shares = 0.0
    entry_price = entry_date = entry_idx = None
    prev_target = None

    equity_list, equity_dates, invested_list, closed_trades = [], [], [], []

    for i in range(len(df)):
        date = df.index[i]
        close = float(df['Close'].iat[i])
        vix_val = float(vix_aligned.iat[i])

        pos_value = shares * close
        eq = cash + pos_value
        equity_list.append(eq)
        equity_dates.append(date)
        invested_list.append(pos_value / eq if eq > 0 else 0.0)

        target = target_alloc(vix_val)

        if prev_target is not None and target != prev_target and i + 1 < len(df):
            next_open = float(df['Open'].iat[i + 1])
            next_date = df.index[i + 1]

            # Close existing shares
            if shares > 0 and entry_price is not None:
                proceeds = shares * next_open
                pnl = proceeds - shares * entry_price
                closed_trades.append({
                    'entry_date': entry_date, 'entry_price': entry_price,
                    'exit_date': next_date, 'exit_price': next_open,
                    'shares': shares, 'pnl': pnl, 'held_days': i + 1 - entry_idx,
                })
                cash += proceeds
                shares = 0.0
                entry_price = entry_date = entry_idx = None

            # Open new position at target allocation
            if target > 0:
                invest = target * cash
                shares = invest / next_open
                cash -= shares * next_open
                entry_price = next_open
                entry_date = next_date
                entry_idx = i + 1

        prev_target = target

    equity_series = pd.Series(equity_list, index=equity_dates)
    vix_series = pd.Series(vix_aligned.values, index=df.index)
    stats = compute_stats(equity_series, initial_capital, closed_trades, df=df)

    trades_csv = fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_vix_regime.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots(df, equity_series, invested_list, vix_series,
                               stats, vix_low, vix_high, out_dir)
        print_stats(stats, initial_capital, equity_series, vix_low, vix_high,
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


def grid_search(ticker='QQQ', period='5y', initial_capital=10000.0,
                vix_low_values=(15, 18, 20, 22, 25),
                vix_high_values=(25, 28, 30, 35, 40),
                maximize='cagr'):
    combos = [(l, h) for l in vix_low_values for h in vix_high_values if l < h]
    print(f'Grid search: {len(combos)} combinations...')
    print('Downloading QQQ and VIX data once...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    raw_vix = fetch_vix(period)
    raw_vix.index = pd.to_datetime(raw_vix.index)
    if raw_df.empty or raw_vix.empty:
        raise ValueError('No data returned.')

    results = []
    for vix_l, vix_h in combos:
        try:
            res = run_backtest_vix_regime(
                initial_capital=initial_capital,
                vix_low=vix_l, vix_high=vix_h,
                verbose=False, df=raw_df, vix_df=raw_vix,
            )
            results.append({
                'vix_low': vix_l, 'vix_high': vix_h,
                'cagr': res['cagr'], 'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'], 'win_rate': res['win_rate'],
                'n_trades': res['n_trades_closed'],
            })
        except Exception as e:
            print(f'  ERROR vix_low={vix_l}, vix_high={vix_h}: {e}')

    results_df = pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)
    print(f'\nAll results by {maximize}:')
    print(results_df.to_string(index=False))

    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nFull results saved to: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best parameters (by {maximize}) ---')
    print(f'  vix_low={best["vix_low"]}, vix_high={best["vix_high"]}')
    print('Running full backtest with best parameters...\n')
    run_backtest_vix_regime(
        initial_capital=initial_capital,
        vix_low=best['vix_low'], vix_high=best['vix_high'],
        verbose=True, df=raw_df, vix_df=raw_vix,
    )
    return results_df


if __name__ == '__main__':
    res = run_backtest_vix_regime(initial_capital=10000.0, vix_low=20, vix_high=30)
    print('\nRESULT:', res)
