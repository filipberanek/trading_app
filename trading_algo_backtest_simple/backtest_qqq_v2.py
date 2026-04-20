"""
Backtest QQQ - Version 2 (simplified peak-drop system)

Rules (documented):

Instrument: QQQ (ETF)
Data: daily, last 5 years (download via yfinance)

Entry:
- Compute the prior peak for each day as the rolling maximum of Close up to previous day.
- If current Close is down at least 3% from that prior peak (i.e. (peak - Close)/peak >= 0.03), signal entry.
- Entry executed at next day's Open.

Position sizing:
- Invest exactly 1% of current account equity (cash+positions) into the trade (no pyramiding).
- Number of shares = (equity * 0.01) / entry_open, capped by available cash.

Exit:
- Exit when Close >= the peak that triggered the entry AND Close > SMA30 (i.e. price recovered above peak and is above 30-day SMA).
- No time limit (hold until exit or end of data).

Assumptions:
- Single position at a time.
- Fractional shares allowed.
- No commissions/slippage.

Outputs:
- Prints: initial capital, final equity, total return, CAGR, arithmetic mean of yearly returns, max drawdown, number of trades, win rate, average PnL.
- Saves `equity_curve_v2.png` and `trades_detail_v2.csv` in this folder.
"""

import os
import math
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
    return df


def run_backtest_v2(initial_capital=10000.0):
    out_dir = os.path.dirname(__file__)
    df = fetch_data('QQQ', period='5y')
    df.index = pd.to_datetime(df.index)

    # if yfinance returned MultiIndex columns (e.g. ('Close','QQQ')), drop second level
    if getattr(df.columns, 'nlevels', 1) > 1:
        df.columns = df.columns.droplevel(1)

    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]

    df['SMA30'] = sma(df['Close'], 30)
    # prior peak: rolling max of Close up to previous day
    df['peak_prior'] = df['Close'].cummax().shift(1)

    dates = df.index

    cash = float(initial_capital)
    position = 0.0
    entry_price = None
    entry_peak = None
    entry_date = None

    equity_list = []
    equity_dates = []
    trades = []

    for i, (today, row) in enumerate(df.iterrows()):
        # compute current equity
        current_price = float(row['Close'])
        total_equity = float(cash + position * current_price)
        equity_list.append(total_equity)
        equity_dates.append(today)

        # if in position, check exit condition
        if position > 0:
            # exit when Close >= entry_peak AND Close > SMA30
            if (current_price >= entry_peak) and (current_price > float(df.iloc[i]['SMA30'])):
                exit_price = current_price
                proceeds = position * exit_price
                pnl = proceeds - position * entry_price
                cash += proceeds
                trades.append({
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'entry_peak': entry_peak,
                    'exit_date': today,
                    'exit_price': exit_price,
                    'shares': position,
                    'pnl': pnl,
                })
                position = 0.0
                entry_price = None
                entry_peak = None
                entry_date = None
            continue

        # not in position: check entry signal on today's close
        peak = df.iloc[i]['peak_prior']
        if pd.isna(peak):
            continue
        close_t = float(row['Close'])
        drop = (peak - close_t) / peak
        if drop >= 0.03:
            # buy at next open
            if i + 1 >= len(df):
                continue
            next_open = float(df.iloc[i + 1]['Open'])
            # compute shares: invest 1% of current equity
            equity_now = total_equity
            invest_amount = equity_now * 0.01
            shares = invest_amount / next_open
            # cap by cash
            max_shares = cash / next_open
            if shares > max_shares:
                shares = max_shares
            if shares <= 0:
                continue

            # execute buy
            cost = shares * next_open
            cash -= cost
            position = shares
            entry_price = next_open
            entry_peak = float(peak)
            entry_date = df.index[i + 1]

    # finalize equity series
    equity_series = pd.Series(equity_list, index=equity_dates)

    # metrics
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_dates[-1] - equity_dates[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan

    # arithmetic mean of annual returns
    # resample yearly: use 'YE' alias for year-end frequency
    yearly = equity_series.resample('YE').last()
    yearly_returns = yearly.pct_change().dropna()
    arith_mean_annual = yearly_returns.mean() if len(yearly_returns) > 0 else np.nan

    md = max_drawdown(equity_series)

    trades_df = pd.DataFrame(trades)
    if len(trades_df) > 0 and 'pnl' in trades_df.columns:
        wins = trades_df[trades_df['pnl'] > 0]
        win_rate = len(wins) / len(trades_df)
        avg_pnl = trades_df['pnl'].mean()
    else:
        win_rate = np.nan
        avg_pnl = np.nan

    # save outputs
    trades_csv = os.path.join(out_dir, 'trades_detail_v2.csv')
    trades_df.to_csv(trades_csv, index=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    equity_series.plot(ax=ax)
    ax.set_title('Equity Curve - QQQ Backtest V2')
    ax.set_ylabel('Account Value')
    ax.grid(True)
    fig_path = os.path.join(out_dir, 'equity_curve_v2.png')
    fig.savefig(fig_path)
    plt.close(fig)

    # Price chart with SMA30 and trade markers
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    df['Close'].plot(ax=ax2, label='Close')
    df['SMA30'].plot(ax=ax2, label='SMA30')
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date'] = pd.to_datetime(trades_df['exit_date'])
        ax2.scatter(trades_df['entry_date'], trades_df['entry_price'], marker='^', color='green', label='Entry', zorder=5)
        ax2.scatter(trades_df['exit_date'], trades_df['exit_price'], marker='v', color='red', label='Exit', zorder=5)
    ax2.set_title('QQQ Price with Trades (V2)')
    ax2.set_ylabel('Price')
    ax2.legend()
    ax2.grid(True)
    price_fig_path = os.path.join(out_dir, 'price_with_trades_v2.png')
    fig2.savefig(price_fig_path)
    plt.close(fig2)

    # print
    print('Backtest V2 summary:')
    print(f'Initial capital: {initial_capital:,.2f}')
    print(f'Final equity: {equity_series.iloc[-1]:,.2f}')
    print(f'Total return: {total_return:.2%}')
    print(f'CAGR: {cagr:.2%}')
    print(f'Arithmetic mean annual return: {(arith_mean_annual if not pd.isna(arith_mean_annual) else np.nan):.2%}')
    print(f'Max drawdown: {md:.2%}')
    print(f'Number of trades: {len(trades_df)}')
    print(f'Win rate: {win_rate if not pd.isna(win_rate) else win_rate}%')
    print(f'Average PnL per trade: {avg_pnl if not pd.isna(avg_pnl) else avg_pnl}')
    print(f'Trades CSV: {trades_csv}')
    print(f'Equity plot: {fig_path}')

    return {
        'initial_capital': initial_capital,
        'final_equity': equity_series.iloc[-1],
        'total_return': total_return,
        'cagr': cagr,
        'arith_mean_annual': arith_mean_annual,
        'max_drawdown': md,
        'n_trades': len(trades_df),
        'win_rate': win_rate,
        'equity_path': fig_path,
        'trades_csv': trades_csv,
    }


if __name__ == '__main__':
    run_backtest_v2(initial_capital=10000.0)
