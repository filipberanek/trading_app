"""
Backtest QQQ/TQQQ - MACD Signal Strategy (with optional leverage)

Rules:
- Instrument: QQQ (or TQQQ for 3x leverage) — controlled by `ticker` param
- Data: daily last 5 years (yfinance)

MACD calculation:
- MACD line  = EMA(fast) - EMA(slow)     defaults: fast=12, slow=26
- Signal line = EMA(signal) of MACD line  default: signal=9
- Histogram   = MACD - Signal

Entry:
- Buy (fully invested) when MACD line crosses ABOVE signal line
  i.e. histogram goes from negative to positive

Exit:
- Sell everything when MACD line crosses BELOW signal line
  i.e. histogram goes from positive to negative

Position sizing:
- Always fully invested when in, 100% cash when out.

Leverage note:
- Use ticker='TQQQ' for 3x leveraged ETF (available from 2010).
  Warning: higher returns but max drawdown typically 50-80%.
- Use ticker='QQQ' for unleveraged (recommended as starting point).

Grid search defaults based on research:
- fast_ema: 8–15 (research optimum ~12)
- slow_ema: 20–30 (research optimum ~26)
- signal_ema: 7–12 (research optimum ~9)

Outputs: backtest_macd_leverage.png, trades_detail_macd_leverage.csv, printed metrics.
"""

import os
import math
import itertools
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt


def ema(series, window):
    return series.ewm(span=window, adjust=False).mean()


def compute_macd(close, fast, slow, signal):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def fetch_data(ticker='QQQ', period='5y'):
    df = yf.download(ticker, period=period, progress=False)
    df = df.dropna()
    if getattr(df.columns, 'nlevels', 1) > 1:
        df.columns = df.columns.droplevel(1)
    return df


def check_entry(histogram_prev, histogram_curr, in_position):
    """
    Returns True when MACD histogram crosses from negative to positive (bullish crossover).
    """
    if in_position:
        return False
    if math.isnan(histogram_prev) or math.isnan(histogram_curr):
        return False
    return histogram_prev < 0 and histogram_curr >= 0


def check_exit(histogram_prev, histogram_curr, in_position):
    """
    Returns True when MACD histogram crosses from positive to negative (bearish crossover).
    """
    if not in_position:
        return False
    if math.isnan(histogram_prev) or math.isnan(histogram_curr):
        return False
    return histogram_prev >= 0 and histogram_curr < 0


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


def print_stats(stats, initial_capital, equity_series, ticker, fast, slow, signal, out_paths):
    print('MACD Leverage backtest summary:')
    print(f'Ticker:                   {ticker}')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'MACD params:              EMA({fast},{slow},{signal})')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    print(f'CAGR buy & hold:          {stats["bh_cagr"]:.2%}' if not pd.isna(stats["bh_cagr"]) else 'CAGR buy & hold:          N/A')
    print(f'Arithmetic mean annual:   {stats["arith_mean_annual"]:.2%}' if not pd.isna(stats["arith_mean_annual"]) else 'Arithmetic mean annual:   N/A')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Number of trades:         {stats["n_trades_closed"]}')
    print(f'Win rate:                 {stats["win_rate"]}')
    print(f'Average PnL per trade:    {stats["avg_pnl"]}')
    print(f'Average return per trade: {stats["avg_trade_return"]:.2%}' if not pd.isna(stats["avg_trade_return"]) else 'Average return per trade: N/A')
    print(f'Max gain per trade:       {stats["max_trade_gain"]:.2%}' if not pd.isna(stats["max_trade_gain"]) else 'Max gain per trade:       N/A')
    print(f'Max drop per trade:       {stats["max_trade_drop"]:.2%}' if not pd.isna(stats["max_trade_drop"]) else 'Max drop per trade:       N/A')
    print(f'Trades CSV:               {out_paths["trades_csv"]}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots(df, equity_series, invested_list, stats, fast, slow, signal, ticker, out_dir):
    """Saves price+MACD, equity, invested% into one PNG. Returns fig path."""
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])

    equity_dates = equity_series.index
    invested_series = pd.Series(invested_list, index=equity_dates)

    fig, (ax_price, ax_macd, ax_equity) = plt.subplots(
        3, 1, sharex=True, figsize=(14, 12),
        gridspec_kw={'height_ratios': [3, 2, 2]}
    )

    # --- price + trades ---
    df['Close'].plot(ax=ax_price, label='Close')
    if len(trades_df) > 0:
        ax_price.scatter(trades_df['entry_date'], trades_df['entry_price'], marker='^', color='green', label='Buy', zorder=5)
        ax_price.scatter(trades_df['exit_date'], trades_df['exit_price'], marker='v', color='red', label='Sell', zorder=5)
    ax_price.set_title(f'Price with Signals - MACD({fast},{slow},{signal}) — {ticker}')
    ax_price.set_ylabel('Price')
    ax_price.legend()
    ax_price.grid(True)

    # --- MACD histogram ---
    df['MACD'].plot(ax=ax_macd, label='MACD', color='blue')
    df['Signal'].plot(ax=ax_macd, label='Signal', color='orange')
    colors = ['green' if v >= 0 else 'red' for v in df['Histogram']]
    ax_macd.bar(df.index, df['Histogram'], color=colors, alpha=0.5, label='Histogram')
    ax_macd.axhline(0, color='black', linewidth=0.8)
    ax_macd.set_title('MACD')
    ax_macd.legend()
    ax_macd.grid(True)

    # --- equity curve ---
    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_macd_leverage.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


def run_backtest_macd_leverage(ticker='QQQ', period='5y', initial_capital=10000.0,
                                fast_ema=12, slow_ema=26, signal_ema=9,
                                verbose=True, df=None):
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    macd_line, signal_line, histogram = compute_macd(df['Close'], fast_ema, slow_ema, signal_ema)
    df['MACD'] = macd_line
    df['Signal'] = signal_line
    df['Histogram'] = histogram

    warmup_done_idx = slow_ema + signal_ema

    cash = float(initial_capital)
    shares = 0.0
    in_position = False
    entry_price = None
    entry_date = None

    equity_list = []
    equity_dates = []
    invested_list = []
    closed_trades = []

    for i in range(len(df)):
        date = df.index[i]
        close = float(df['Close'].iat[i])

        hist_curr = float(df['Histogram'].iat[i]) if not pd.isna(df['Histogram'].iat[i]) else math.nan
        hist_prev = float(df['Histogram'].iat[i - 1]) if i > 0 and not pd.isna(df['Histogram'].iat[i - 1]) else math.nan

        pos_value = shares * close
        eq = cash + pos_value
        equity_list.append(eq)
        equity_dates.append(date)
        invested_list.append(pos_value / eq if eq > 0 else 0.0)

        warmup_done = i >= warmup_done_idx

        if warmup_done and check_exit(hist_prev, hist_curr, in_position):
            exit_price = close
            proceeds = shares * exit_price
            pnl = proceeds - shares * entry_price
            cash += proceeds
            closed_trades.append({
                'entry_date': entry_date, 'entry_price': entry_price,
                'exit_date': date, 'exit_price': exit_price,
                'shares': shares, 'pnl': pnl,
            })
            shares = 0.0
            in_position = False
            entry_price = None
            entry_date = None

        if warmup_done and check_entry(hist_prev, hist_curr, in_position):
            if i + 1 < len(df):
                next_open = float(df['Open'].iat[i + 1])
                shares = cash / next_open
                cash -= shares * next_open
                in_position = True
                entry_price = next_open
                entry_date = df.index[i + 1]

    equity_series = pd.Series(equity_list, index=equity_dates)
    stats = compute_stats(equity_series, initial_capital, closed_trades, df=df)

    trades_csv = None
    fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_macd_leverage.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots(df, equity_series, invested_list, stats, fast_ema, slow_ema, signal_ema, ticker, out_dir)
        out_paths = {'trades_csv': trades_csv, 'fig_path': fig_path}
        print_stats(stats, initial_capital, equity_series, ticker, fast_ema, slow_ema, signal_ema, out_paths)

    def _f(v):
        return round(float(v), 3) if not pd.isna(v) else None

    return {
        'initial_capital': float(initial_capital),
        'ticker': ticker,
        'fast_ema': fast_ema, 'slow_ema': slow_ema, 'signal_ema': signal_ema,
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
                fast_ema_values=(4, 8, 10, 12, 15),
                slow_ema_values=(20, 24, 26, 30, 45),
                signal_ema_values=(4, 7, 9, 12),
                maximize='cagr'):
    """
    Grid search over MACD parameters.
    Research optimum: fast=12, slow=26, signal=9 (classic settings).
    """
    combos = list(itertools.product(fast_ema_values, slow_ema_values, signal_ema_values))
    combos = [(f, s, sig) for f, s, sig in combos if f < s]
    total = len(combos)
    print(f'Grid search: {total} combinations...')
    print(f'Downloading data ({ticker})...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if raw_df.empty:
        raise ValueError('No data returned.')

    results = []
    for idx, (fast, slow, sig) in enumerate(combos, 1):
        try:
            res = run_backtest_macd_leverage(
                ticker=ticker, initial_capital=initial_capital,
                fast_ema=fast, slow_ema=slow, signal_ema=sig,
                verbose=False, df=raw_df,
            )
            results.append({
                'fast_ema': fast, 'slow_ema': slow, 'signal_ema': sig,
                'cagr': res['cagr'],
                'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'],
                'win_rate': res['win_rate'],
                'n_trades': res['n_trades_closed'],
                'avg_trade_return': res['avg_trade_return'],
            })
        except Exception as e:
            print(f'  [{idx}/{total}] ERROR {fast},{slow},{sig}: {e}')

        if idx % 10 == 0:
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
    print(f'  fast={int(best["fast_ema"])}, slow={int(best["slow_ema"])}, signal={int(best["signal_ema"])}')
    print('Running full backtest with best parameters...\n')
    run_backtest_macd_leverage(
        ticker=ticker, initial_capital=initial_capital,
        fast_ema=int(best['fast_ema']),
        slow_ema=int(best['slow_ema']),
        signal_ema=int(best['signal_ema']),
        verbose=True, df=raw_df,
    )

    return results_df


if __name__ == '__main__':
    # QQQ = unleveraged, TQQQ = 3x leveraged (higher risk)
    #res = run_backtest_macd_leverage(ticker='QQQ', initial_capital=10000.0, fast_ema=12, slow_ema=26, signal_ema=9)
    #print('\nRESULT:', res)
    grid_search()