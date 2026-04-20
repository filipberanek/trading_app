"""
Backtest QQQ - Scale-in Simple

Rules (version):
- Instrument: QQQ
- Data: daily last 5 years (yfinance)

Entry / scale-in:
- Compute prior peak (rolling max up to previous day).
- Define bin size `bin_size_pct` (default 3%) and `max_drop_pct` (default 25%).
- Bins = multiples of bin_size_pct: 3%,6%,9%... up to max_drop_pct.
- Cumulative allocation schedule: linear ramp from `initial_alloc_pct` (default 5%) at first bin to 100% at last bin.
- When current drop from current prior-peak >= some bin, invest the incremental allocation corresponding to that bin at next day's Open. If multiple bins crossed at once, invest cumulative needed to reach that bin.

Exit:
- Track running max of SMA_exit over all history (sma_running_max).
- Exit when Close > sma_running_max AND Close < current SMA_exit (both required simultaneously), OR after `max_hold_days` (default 5) close at that day's Close.

Position sizing:
- Invest percent of current equity equal to incremental allocation percent (cumulative schedule) at the time of entry. Fractional shares allowed. No leverage; cap by available cash.

Outputs:
- `equity_curve_scalein.png`, `price_with_trades_scalein.png`, `trades_detail_scalein.csv` and printed metrics.

Parameters are exposed near top of `run_backtest_scalein()`; you can tweak `bin_size_pct`, `max_drop_pct`, `initial_alloc_pct`, `initial_capital`.
"""

import os
import math
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt


def sma(series, window):
    return series.rolling(window).mean()


def max_drawdown(equity):
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    return drawdown.min()


def fetch_data(ticker='QQQ', period='5y'):
    df = yf.download(ticker, period=period, progress=False)
    df = df.dropna()
    # normalize multiindex columns
    if getattr(df.columns, 'nlevels', 1) > 1:
        df.columns = df.columns.droplevel(1)
    return df


def check_entry(close, peak, thresholds, cumul, allocated_cum_for_peak, eq, cash):
    """
    Returns (should_enter, incremental_fraction, desired_cum).
    incremental_fraction = fraction of equity to invest at next open.
    """
    if pd.isna(peak) or peak <= 0:
        return False, 0.0, allocated_cum_for_peak

    drop = (peak - close) / peak
    reached_idx = -1
    for idx, th in enumerate(thresholds):
        if drop >= th:
            reached_idx = idx
        else:
            break

    if reached_idx < 0:
        return False, 0.0, allocated_cum_for_peak

    desired_cum = cumul[reached_idx]
    incremental_needed = desired_cum - allocated_cum_for_peak
    if incremental_needed <= 1e-12 or cash <= 0:
        return False, 0.0, desired_cum

    invest_amount = min(incremental_needed * eq, cash)
    return True, invest_amount, desired_cum


def check_exit(close, sma_current, sma_max_at_entry, has_open_positions):
    """
    Returns True if exit conditions are met:
    - has_open_positions is True
    - close > sma_max_at_entry (above SMA high frozen at trade entry)
    - close < sma_current      (below current SMA)
    All conditions must be true simultaneously.
    """
    if not has_open_positions:
        return False
    if math.isnan(sma_current) or sma_max_at_entry == float('-inf'):
        return False
    return (close > sma_max_at_entry) and (close < sma_current)


def compute_stats(equity_series, initial_capital, closed_trades, df=None):
    """Returns dict of performance metrics."""
    trades_df = pd.DataFrame(closed_trades)

    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan

    if df is not None and years > 0:
        bh_cagr = (float(df['Close'].iloc[-1]) / float(df['Close'].iloc[0])) ** (1 / years) - 1
    else:
        bh_cagr = np.nan
    yearly = equity_series.resample('YE').last()
    yearly_returns = yearly.pct_change().dropna()
    arith_mean_annual = yearly_returns.mean() if len(yearly_returns) > 0 else np.nan
    md = max_drawdown(equity_series)

    if len(trades_df) > 0 and 'pnl' in trades_df.columns:
        win_rate = len(trades_df[trades_df['pnl'] > 0]) / len(trades_df)
        avg_pnl = trades_df['pnl'].mean()
        trade_returns = (trades_df['exit_price'] - trades_df['entry_price']) / trades_df['entry_price']
        avg_trade_return = trade_returns.mean()
        max_trade_gain = trade_returns.max()
        max_trade_drop = trade_returns.min()
    else:
        win_rate = np.nan
        avg_pnl = np.nan
        avg_trade_return = np.nan
        max_trade_gain = np.nan
        max_trade_drop = np.nan

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
        'trades_df': trades_df,
    }


def print_stats(stats, initial_capital, equity_series, out_paths):
    """Prints backtest summary to stdout."""
    print('Scale-in backtest summary:')
    print(f'Initial capital: {initial_capital:,.2f}')
    print(f'Final equity: {equity_series.iloc[-1]:,.2f}')
    print(f'Total return: {stats["total_return"]:.2%}')
    print(f'CAGR: {stats["cagr"]:.2%}')
    print(f'Arithmetic mean annual return: {stats["arith_mean_annual"]:.2%}' if not pd.isna(stats["arith_mean_annual"]) else 'Arithmetic mean annual return: N/A')
    print(f'Max drawdown: {stats["max_drawdown"]:.2%}')
    print(f'Number of trades: {stats["n_trades_closed"]}')
    print(f'Win rate: {stats["win_rate"]}')
    print(f'Average PnL per trade: {stats["avg_pnl"]}')
    print(f'Average return per trade: {stats["avg_trade_return"]:.2%}' if not pd.isna(stats["avg_trade_return"]) else 'Average return per trade: N/A')
    print(f'Max gain per trade:       {stats["max_trade_gain"]:.2%}' if not pd.isna(stats["max_trade_gain"]) else 'Max gain per trade: N/A')
    print(f'Max drop per trade:       {stats["max_trade_drop"]:.2%}' if not pd.isna(stats["max_trade_drop"]) else 'Max drop per trade: N/A')
    print(f'Trades CSV: {out_paths["trades_csv"]}')
    print(f'Equity plot: {out_paths["eq_fig"]}')
    print(f'Price plot: {out_paths["price_fig"]}')


def save_plots(df, equity_series, alloc_pct_list, num_pos_list, open_trades, stats, exit_sma_window, out_dir):
    """Saves all three subplots (price, equity, allocation) into one PNG. Returns fig path."""
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])

    equity_dates = equity_series.index
    alloc_series = pd.Series(alloc_pct_list, index=equity_dates)
    numpos_series = pd.Series(num_pos_list, index=equity_dates)

    fig, (ax_price, ax_equity, ax_alloc) = plt.subplots(
        3, 1, sharex=True, figsize=(14, 12),
        gridspec_kw={'height_ratios': [3, 2, 1]}
    )

    # --- price + trades ---
    df['Close'].plot(ax=ax_price, label='Close')
    df['SMA_exit'].plot(ax=ax_price, label=f'SMA{exit_sma_window}')
    if len(trades_df) > 0:
        ax_price.scatter(trades_df['entry_date'], trades_df['entry_price'], marker='^', color='green', label='Entry', zorder=5)
        ax_price.scatter(trades_df['exit_date'], trades_df['exit_price'], marker='v', color='red', label='Exit', zorder=5)
    for t in open_trades:
        ax_price.scatter(t['entry_date'], t['entry_price'], marker='^', color='orange', zorder=6)
    ax_price.set_title('Price with Trades - Scale-in')
    ax_price.set_ylabel('Price')
    ax_price.legend()
    ax_price.grid(True)

    # --- equity curve ---
    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    # --- allocation % + open positions ---
    ax_alloc.fill_between(alloc_series.index, alloc_series.values * 100, step='post', alpha=0.3, label='Allocated %')
    ax_alloc.set_ylabel('Allocated %')
    ax_alloc.set_ylim(0, 105)
    ax_alloc.grid(True)
    ax_alloc.legend(loc='upper left')
    ax_alloc2 = ax_alloc.twinx()
    ax_alloc2.step(numpos_series.index, numpos_series.values, where='post', color='tab:orange', label='Open positions')
    ax_alloc2.set_ylabel('Open positions')
    ax_alloc2.legend(loc='upper right')

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_scalein.png')
    fig.savefig(out_fig)
    plt.close(fig)

    return out_fig


def build_bins(bin_size_pct, max_drop_pct, initial_alloc_pct):
    # bin_size_pct, max_drop_pct, initial_alloc_pct are fractions (0.03, 0.25, 0.05)
    n_bins = int(max_drop_pct // bin_size_pct)
    if n_bins < 1:
        n_bins = 1
    thresholds = [bin_size_pct * k for k in range(1, n_bins + 1)]
    # cumulative allocation schedule: linear from initial_alloc to 1.0
    if n_bins == 1:
        cumul = [1.0]
    else:
        cumul = [initial_alloc_pct + (k) / (n_bins - 1) * (1.0 - initial_alloc_pct) for k in range(0, n_bins)]
    # incremental allocations
    incr = []
    prev = 0.0
    for c in cumul:
        incr.append(c - prev)
        prev = c
    return thresholds, cumul, incr


def run_backtest_scalein(ticker='QQQ', period='5y', initial_capital=10000.0,
                         bin_size_pct=0.03, max_drop_pct=0.25, initial_alloc_pct=0.05,
                         exit_sma_window=5, verbose=True, df=None):
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    # SMA used for exit (parameterizable)
    df['SMA_exit'] = sma(df['Close'], exit_sma_window)
    df['peak_prior'] = df['Close'].cummax().shift(1)

    thresholds, cumul, incr = build_bins(bin_size_pct, max_drop_pct, initial_alloc_pct)

    cash = float(initial_capital)
    open_trades = []  # list of dicts: entry_idx, entry_date, entry_price, shares
    closed_trades = []

    equity_list = []
    equity_dates = []
    alloc_pct_list = []
    num_pos_list = []

    # state for current peak
    current_peak = None
    allocated_cum_for_peak = 0.0
    sma_running_max = float('-inf')

    for i in range(len(df)):
        date = df.index[i]
        close = float(df['Close'].iat[i])
        sma_exit_val = df['SMA_exit'].iat[i]
        sma_exit = float(sma_exit_val) if not pd.isna(sma_exit_val) else np.nan

        # update running max of SMA_exit
        if not math.isnan(sma_exit):
            sma_running_max = max(sma_running_max, sma_exit)

        # wait until SMA has enough bars to be valid (exit_sma_window + 1)
        warmup_done = i >= exit_sma_window

        # compute equity and tracking stats
        pos_value = sum(t['shares'] * close for t in open_trades)
        eq = cash + pos_value
        equity_list.append(eq)
        equity_dates.append(date)
        alloc_pct_list.append((pos_value / eq) if eq > 0 else 0.0)
        num_pos_list.append(len(open_trades))

        # check exits for each open trade
        for t in open_trades[:]:
            held_days = i - t['entry_idx']
            if warmup_done and check_exit(close, sma_exit, t['sma_max_at_entry'], has_open_positions=len(open_trades) > 0):
                exit_price = close
                proceeds = t['shares'] * exit_price
                pnl = proceeds - t['shares'] * t['entry_price']
                cash += proceeds
                closed_trades.append({
                    'entry_date': t['entry_date'], 'entry_price': t['entry_price'],
                    'exit_date': date, 'exit_price': exit_price,
                    'shares': t['shares'], 'pnl': pnl, 'held_days': held_days,
                    'entry_peak': t.get('entry_peak', np.nan)
                })
                open_trades.remove(t)

        # check entry signal
        peak = df['peak_prior'].iat[i]
        if pd.isna(peak):
            continue
        if current_peak is None or peak != current_peak:
            current_peak = peak
            allocated_cum_for_peak = 0.0

        should_enter, invest_amount, desired_cum = check_entry(
            close, peak, thresholds, cumul, allocated_cum_for_peak, eq, cash
        ) if warmup_done else (False, 0.0, allocated_cum_for_peak)
        allocated_cum_for_peak = desired_cum

        if should_enter:
            if i + 1 >= len(df):
                continue
            next_open = float(df['Open'].iat[i + 1])
            shares = invest_amount / next_open
            cash -= shares * next_open
            open_trades.append({
                'entry_idx': i + 1,
                'entry_date': df.index[i + 1],
                'entry_price': next_open,
                'shares': shares,
                'entry_peak': peak,
                'sma_max_at_entry': sma_running_max,
            })

    equity_series = pd.Series(equity_list, index=equity_dates)

    stats = compute_stats(equity_series, initial_capital, closed_trades, df=df)

    trades_csv = None
    fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_scalein.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots(df, equity_series, alloc_pct_list, num_pos_list, open_trades, stats, exit_sma_window, out_dir)
        out_paths = {'trades_csv': trades_csv, 'eq_fig': fig_path, 'price_fig': fig_path}
        print_stats(stats, initial_capital, equity_series, out_paths)

    def _f(v):
        return round(float(v), 3) if not pd.isna(v) else None

    return {
        'initial_capital': float(initial_capital),
        'final_equity': _f(equity_series.iloc[-1]),
        'total_return': _f(stats['total_return']),
        'cagr': _f(stats['cagr']),
        'bh_cagr': _f(stats['bh_cagr']),
        'arith_mean_annual': _f(stats['arith_mean_annual']),
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
                bin_size_pct_values=(0.05, 0.07, 0.1, 0.12, 0.15),
                max_drop_pct_values=( 0.10, 0.15, 0.20, 0.30),
                initial_alloc_pct_values=(0.10, 0.20, 0.30, 0.40, 0.50),
                exit_sma_window_values=(30, 50, 60, 75),
                maximize='cagr'):
    """
    Grid search over backtest parameters. Returns sorted DataFrame of results.
    maximize: 'cagr' | 'total_return' | 'win_rate'
    """
    import itertools

    combos = list(itertools.product(
        bin_size_pct_values,
        max_drop_pct_values,
        initial_alloc_pct_values,
        exit_sma_window_values,
    ))
    total = len(combos)
    print(f'Grid search: {total} combinations...')

    results = []
    for idx, (bin_size, max_drop, init_alloc, sma_win) in enumerate(combos, 1):
        if bin_size >= max_drop:
            continue
        try:
            res = run_backtest_scalein(
                ticker=ticker, period=period, initial_capital=initial_capital,
                bin_size_pct=bin_size, max_drop_pct=max_drop,
                initial_alloc_pct=init_alloc, exit_sma_window=sma_win,
                verbose=False,
            )
            results.append({
                'bin_size_pct': bin_size,
                'max_drop_pct': max_drop,
                'initial_alloc_pct': init_alloc,
                'exit_sma_window': sma_win,
                'cagr': res['cagr'],
                'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'],
                'win_rate': res['win_rate'],
                'n_trades': res['n_trades_closed'],
                'avg_trade_return': res['avg_trade_return'],
            })
        except Exception as e:
            print(f'  [{idx}/{total}] ERROR {bin_size},{max_drop},{init_alloc},{sma_win}: {e}')

        if idx % 50 == 0:
            print(f'  {idx}/{total} done...')

    results_df = pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)

    print(f'\nTop 10 by {maximize}:')
    print(results_df.head(10).to_string(index=False))

    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nFull results saved to: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best parameters (by {maximize}) ---')
    print(f'  bin_size_pct={best["bin_size_pct"]}, max_drop_pct={best["max_drop_pct"]}, '
          f'initial_alloc_pct={best["initial_alloc_pct"]}, exit_sma_window={int(best["exit_sma_window"])}')
    print('Running full backtest with best parameters...\n')
    run_backtest_scalein(
        ticker=ticker, period=period, initial_capital=initial_capital,
        bin_size_pct=best['bin_size_pct'],
        max_drop_pct=best['max_drop_pct'],
        initial_alloc_pct=best['initial_alloc_pct'],
        exit_sma_window=int(best['exit_sma_window']),
        verbose=True,
    )

    return results_df


if __name__ == '__main__':
    # default params; tweak bin_size_pct or initial_alloc_pct as desired
    #res = run_backtest_scalein(initial_capital=10000.0, bin_size_pct=0.02, max_drop_pct=0.2, initial_alloc_pct=0.3, exit_sma_window=30)
    #print('\nRESULT:', res)
    grid_search()