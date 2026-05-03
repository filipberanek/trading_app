"""
Backtest QQQ - Pure Buy the Dip

Rules:
- Instrument: QQQ
- Data: daily last 5 years (yfinance)

Entry:
- Single full position (100% of available cash) when Close drops >= drop_pct from prior peak.
- Buy at next day's Open.
- Only one position at a time — no scale-in.

Exit:
- Close >= prior_peak at entry  (price fully recovered to the peak that triggered entry)
- Exit at that day's Close.

Position sizing:
- Fully invested on entry, fully out on exit.
- Only in market during dips — expected time in market ~15-20%.

Grid search defaults based on research (S&P 500 study):
- drop_pct: 2–10%  (research: 5% drop gave 76% win rate, 16% time in market)

Outputs: backtest_buy_the_dip.png, trades_detail_buy_the_dip.csv, printed metrics.
"""

import os
import math
import itertools
import pandas as pd
import numpy as np
import sys
import matplotlib.pyplot as plt

_ALGO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ALGO_ROOT not in sys.path:
    sys.path.insert(0, _ALGO_ROOT)
from data_loader import load_ohlcv


def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def fetch_data(ticker='QQQ', period='5y'):
    return load_ohlcv(ticker, period=period)


def check_entry(close, peak, drop_pct, in_position):
    """
    Returns True when not in position and close has dropped >= drop_pct from prior peak.
    """
    if in_position:
        return False
    if pd.isna(peak) or peak <= 0:
        return False
    return (peak - close) / peak >= drop_pct


def check_exit(close, entry_peak, in_position):
    """
    Returns True when in position and close has recovered to or above the entry peak.
    """
    if not in_position:
        return False
    if pd.isna(entry_peak):
        return False
    return close >= entry_peak


def compute_stats(equity_series, initial_capital, closed_trades, df=None):
    """Returns dict of performance metrics."""
    trades_df = pd.DataFrame(closed_trades)

    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    yearly = equity_series.resample('YE').last()
    yearly_returns = yearly.pct_change().dropna()
    arith_mean_annual = yearly_returns.mean() if len(yearly_returns) > 0 else np.nan
    md = max_drawdown(equity_series)

    if df is not None and years > 0:
        bh_cagr = (float(df['Close'].iloc[-1]) / float(df['Close'].iloc[0])) ** (1 / years) - 1
    else:
        bh_cagr = np.nan

    if len(trades_df) > 0 and 'pnl' in trades_df.columns:
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df)
        avg_pnl = trades_df['pnl'].mean()
        trade_returns = (trades_df['exit_price'] - trades_df['entry_price']) / trades_df['entry_price']
        avg_trade_return = trade_returns.mean()
        max_trade_gain = trade_returns.max()
        max_trade_drop = trade_returns.min()
        time_in_market = trades_df['held_days'].sum() / len(equity_series) if len(equity_series) > 0 else np.nan
    else:
        win_rate = np.nan
        avg_pnl = np.nan
        avg_trade_return = np.nan
        max_trade_gain = np.nan
        max_trade_drop = np.nan
        time_in_market = np.nan

    return {
        'total_return': total_return,
        'cagr': cagr,
        'bh_cagr': bh_cagr,
        'arith_mean_annual': arith_mean_annual,
        'max_drawdown': md,
        'n_trades_closed': len(trades_df),
        'win_rate': win_rate,
        'avg_pnl': avg_pnl,
        'avg_trade_return': avg_trade_return,
        'max_trade_gain': max_trade_gain,
        'max_trade_drop': max_trade_drop,
        'time_in_market': time_in_market,
        'trades_df': trades_df,
    }


def print_stats(stats, initial_capital, equity_series, drop_pct, out_paths):
    print('Buy the Dip backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'Drop threshold:           {drop_pct:.1%}')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    print(f'CAGR buy & hold:          {stats["bh_cagr"]:.2%}' if not pd.isna(stats["bh_cagr"]) else 'CAGR buy & hold:          N/A')
    print(f'Arithmetic mean annual:   {stats["arith_mean_annual"]:.2%}' if not pd.isna(stats["arith_mean_annual"]) else 'Arithmetic mean annual:   N/A')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Time in market:           {stats["time_in_market"]:.1%}' if not pd.isna(stats["time_in_market"]) else 'Time in market:           N/A')
    print(f'Number of trades:         {stats["n_trades_closed"]}')
    print(f'Win rate:                 {stats["win_rate"]}')
    print(f'Average PnL per trade:    {stats["avg_pnl"]}')
    print(f'Average return per trade: {stats["avg_trade_return"]:.2%}' if not pd.isna(stats["avg_trade_return"]) else 'Average return per trade: N/A')
    print(f'Max gain per trade:       {stats["max_trade_gain"]:.2%}' if not pd.isna(stats["max_trade_gain"]) else 'Max gain per trade:       N/A')
    print(f'Max drop per trade:       {stats["max_trade_drop"]:.2%}' if not pd.isna(stats["max_trade_drop"]) else 'Max drop per trade:       N/A')
    print(f'Trades CSV:               {out_paths["trades_csv"]}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots(df, equity_series, invested_list, stats, drop_pct, out_dir):
    """Saves price+trades, equity, invested% into one PNG. Returns fig path."""
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])

    equity_dates = equity_series.index
    invested_series = pd.Series(invested_list, index=equity_dates)

    fig, (ax_price, ax_equity, ax_inv) = plt.subplots(
        3, 1, sharex=True, figsize=(14, 12),
        gridspec_kw={'height_ratios': [3, 2, 1]}
    )

    df['Close'].plot(ax=ax_price, label='Close')
    df['peak_prior'].plot(ax=ax_price, label='Prior Peak', color='orange', linestyle='--', linewidth=1)
    if len(trades_df) > 0:
        ax_price.scatter(trades_df['entry_date'], trades_df['entry_price'], marker='^', color='green', label='Buy', zorder=5)
        ax_price.scatter(trades_df['exit_date'], trades_df['exit_price'], marker='v', color='red', label='Sell', zorder=5)
    ax_price.set_title(f'Price with Trades - Buy the Dip ({drop_pct:.0%} drop)')
    ax_price.set_ylabel('Price')
    ax_price.legend()
    ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    ax_inv.fill_between(invested_series.index, invested_series.values * 100, step='post', alpha=0.4, color='steelblue', label='Invested %')
    ax_inv.set_ylabel('Invested %')
    ax_inv.set_ylim(0, 105)
    ax_inv.grid(True)
    ax_inv.legend()

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_buy_the_dip.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


def run_backtest_buy_the_dip(ticker='QQQ', period='5y', initial_capital=10000.0,
                              drop_pct=0.05, verbose=True, df=None):
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    df['peak_prior'] = df['Close'].cummax().shift(1)

    cash = float(initial_capital)
    shares = 0.0
    in_position = False
    entry_price = None
    entry_peak = None
    entry_date = None
    entry_idx = None

    equity_list = []
    equity_dates = []
    invested_list = []
    closed_trades = []

    for i in range(len(df)):
        date = df.index[i]
        close = float(df['Close'].iat[i])
        peak = df['peak_prior'].iat[i]

        pos_value = shares * close
        eq = cash + pos_value
        equity_list.append(eq)
        equity_dates.append(date)
        invested_list.append(pos_value / eq if eq > 0 else 0.0)

        if check_exit(close, entry_peak, in_position):
            exit_price = close
            proceeds = shares * exit_price
            pnl = proceeds - shares * entry_price
            held_days = i - entry_idx
            cash += proceeds
            closed_trades.append({
                'entry_date': entry_date, 'entry_price': entry_price,
                'exit_date': date, 'exit_price': exit_price,
                'shares': shares, 'pnl': pnl, 'held_days': held_days,
                'entry_peak': entry_peak,
            })
            shares = 0.0
            in_position = False
            entry_price = None
            entry_peak = None
            entry_date = None
            entry_idx = None

        if check_entry(close, peak, drop_pct, in_position):
            if i + 1 < len(df):
                next_open = float(df['Open'].iat[i + 1])
                shares = cash / next_open
                cash -= shares * next_open
                in_position = True
                entry_price = next_open
                entry_peak = float(peak)
                entry_date = df.index[i + 1]
                entry_idx = i + 1

    equity_series = pd.Series(equity_list, index=equity_dates)
    stats = compute_stats(equity_series, initial_capital, closed_trades, df=df)

    trades_csv = None
    fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_buy_the_dip.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots(df, equity_series, invested_list, stats, drop_pct, out_dir)
        out_paths = {'trades_csv': trades_csv, 'fig_path': fig_path}
        print_stats(stats, initial_capital, equity_series, drop_pct, out_paths)

    def _f(v):
        return round(float(v), 3) if not pd.isna(v) else None

    return {
        'initial_capital': float(initial_capital),
        'drop_pct': drop_pct,
        'final_equity': _f(equity_series.iloc[-1]),
        'total_return': _f(stats['total_return']),
        'cagr': _f(stats['cagr']),
        'bh_cagr': _f(stats['bh_cagr']),
        'arith_mean_annual': _f(stats['arith_mean_annual']),
        'max_drawdown': _f(stats['max_drawdown']),
        'time_in_market': _f(stats['time_in_market']),
        'n_trades_closed': int(stats['n_trades_closed']),
        'win_rate': _f(stats['win_rate']),
        'avg_trade_return': _f(stats['avg_trade_return']),
        'max_trade_gain': _f(stats['max_trade_gain']),
        'max_trade_drop': _f(stats['max_trade_drop']),
        'fig_path': fig_path,
        'trades_csv': trades_csv,
    }


def grid_search(ticker='QQQ', period='5y', initial_capital=10000.0,
                drop_pct_values=(0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20),
                maximize='cagr'):
    """
    Grid search over drop threshold.
    Research: 5% drop → 76% win rate, 16% time in market on S&P 500.
    """
    print(f'Grid search: {len(drop_pct_values)} combinations...')
    print('Downloading data once...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if raw_df.empty:
        raise ValueError('No data returned.')

    results = []
    for drop in drop_pct_values:
        try:
            res = run_backtest_buy_the_dip(
                initial_capital=initial_capital,
                drop_pct=drop, verbose=False, df=raw_df,
            )
            results.append({
                'drop_pct': drop,
                'cagr': res['cagr'],
                'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'],
                'win_rate': res['win_rate'],
                'n_trades': res['n_trades_closed'],
                'time_in_market': res['time_in_market'],
                'avg_trade_return': res['avg_trade_return'],
            })
        except Exception as e:
            print(f'  ERROR drop={drop}: {e}')

    results_df = pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)

    print(f'\nAll results by {maximize}:')
    print(results_df.to_string(index=False))

    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nFull results saved to: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best parameters (by {maximize}) ---')
    print(f'  drop_pct={best["drop_pct"]:.1%}')
    print('Running full backtest with best parameters...\n')
    run_backtest_buy_the_dip(
        initial_capital=initial_capital,
        drop_pct=best['drop_pct'],
        verbose=True, df=raw_df,
    )

    return results_df


if __name__ == '__main__':
    res = run_backtest_buy_the_dip(initial_capital=10000.0, drop_pct=0.05)
    print('\nRESULT:', res)
