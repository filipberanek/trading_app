"""
Backtest QQQ - Version 1

Detailed rules (documented here):

Instrument: QQQ (ETF)
Data: daily closes/opens for last 5 years (downloaded via yfinance)

Entry rules:
- At day t, require Close[t] > SMA200[t]
- 3-day return ending at t: Close[t] / Close[t-3] - 1 <= -3.0%  (i.e. 3-day drop >= 3%)
- If the above holds, buy at next day's Open (t+1 Open)

Position sizing:
- Target price used for sizing is SMA5 computed at day t (the day signal formed).
- If Target <= entry_open, skip the trade (no profitable exit possible under Exit B condition).
- Number of shares = (capital * 0.01) / (target_price - entry_open)
- Cap shares so that no leverage is used (position_value <= cash). Fractional shares allowed for simulation.

Exit rules (Version 1, Exit B with profit condition):
- Exit at first day j >= entry day when Close[j] >= SMA5[j] AND Close[j] > entry_open
- Additionally a `MAX_HOLD_DAYS` limit (default 5) is enforced — if not exited earlier, position is closed at that day's Close.

Assumptions and simplifications:
- No commissions/slippage in base simulation (can be added)
- Fractional shares allowed
- No intraday execution differences besides using next-day Open for entry and daily Close for exit checks

Outputs:
- Prints metrics: total return, annualized return, max drawdown, number of trades, win rate
- Saves `equity_curve.png` and `trades_detail.csv` in this folder

"""

import os
import math
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt


def sma(series, window):
    return series.rolling(window).mean()


def atr(df, n=10):
    high = df['High']
    low = df['Low']
    close = df['Close']
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def max_drawdown(equity):
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max
    md = drawdown.min()
    return md


def fetch_data(ticker='QQQ', period='5y'):
    df = yf.download(ticker, period=period, progress=False)
    df = df.dropna()
    return df


def run_backtest(initial_capital=100000.0, max_hold_days=5):
    out_dir = os.path.dirname(__file__)
    df = fetch_data('QQQ', period='5y')
    df.index = pd.to_datetime(df.index)
    cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if 'Adj Close' in df.columns:
        cols.insert(4, 'Adj Close')
    df = df[[c for c in cols if c in df.columns]]

    df['SMA200'] = sma(df['Close'], 200)
    df['SMA5'] = sma(df['Close'], 5)
    df['ATR10'] = atr(df, 10)

    dates = df.index
    cash = initial_capital
    equity = []
    equity_dates = []

    trades = []

    position = 0.0
    entry_price = None
    entry_date = None
    target_price = None
    entry_idx = None

    for i in range(len(df)):
        today = dates[i]
        row = df.iloc[i]

        # update equity
        try:
            current_price = float(row['Close'])
        except Exception:
            current_price = float(row['Adj Close']) if 'Adj Close' in df.columns else 0.0
        total_equity = float(cash + position * current_price)
        equity.append(total_equity)
        equity_dates.append(today)

        # if in position, check exit
        if position > 0:
            # Check exit B: Close >= SMA5 and Close > entry_open
            if (row['Close'] >= df['SMA5'].iloc[i]) and (row['Close'] > entry_price):
                exit_price = row['Close']
                proceeds = position * exit_price
                pnl = proceeds - position * entry_price
                cash += proceeds
                trades.append({
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_date': today,
                    'exit_price': exit_price,
                    'shares': position,
                    'pnl': pnl,
                })
                position = 0.0
                entry_price = None
                entry_date = None
                target_price = None
                entry_idx = None
                continue

            # max hold
            if entry_idx is not None and (i - entry_idx) >= max_hold_days:
                exit_price = row['Close']
                proceeds = position * exit_price
                pnl = proceeds - position * entry_price
                cash += proceeds
                trades.append({
                    'entry_date': entry_date,
                    'entry_price': entry_price,
                    'exit_date': today,
                    'exit_price': exit_price,
                    'shares': position,
                    'pnl': pnl,
                })
                position = 0.0
                entry_price = None
                entry_date = None
                target_price = None
                entry_idx = None
                continue

            # otherwise hold
            continue

        # if not in position, check entry signal based on today's close
        # need at least 200 + 3 days
        if i < 200 or i < 3:
            continue

        try:
            close_t = float(row['Close'])
            sma200_t = float(row['SMA200'])
            prev3_close = float(df.iloc[i - 3]['Close'])
        except Exception:
            continue

        # Entry conditions
        three_day_return = close_t / prev3_close - 1.0
        if (close_t > sma200_t) and (three_day_return <= -0.03):
            # plan to buy at next day's open
            if i + 1 >= len(df):
                continue
            next_open = df['Open'].iloc[i + 1]
            # use SMA5 at day t as target estimate
            target = df['SMA5'].iloc[i]
            if math.isnan(target):
                continue
            # require target > entry_open to ensure profitable exit under Exit B
            if target <= next_open:
                continue

            # compute shares so profit at target equals 1% of current capital
            desired_profit = 0.01 * cash
            price_diff = target - next_open
            if price_diff <= 0:
                continue
            shares = desired_profit / price_diff
            # ensure no leverage: position cost <= cash
            max_shares_affordable = cash / next_open
            if shares > max_shares_affordable:
                shares = max_shares_affordable
            if shares <= 0:
                continue

            # execute buy at next_open
            cost = shares * next_open
            cash -= cost
            position = shares
            entry_price = next_open
            entry_date = df.index[i + 1]
            target_price = target
            entry_idx = i + 1

    # final equity array
    equity_series = pd.Series(equity, index=equity_dates)

    # compute metrics
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_dates[-1] - equity_dates[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    md = max_drawdown(equity_series)

    trades_df = pd.DataFrame(trades)
    if 'pnl' in trades_df.columns and len(trades_df) > 0:
        wins = trades_df[trades_df['pnl'] > 0]
        win_rate = len(wins) / len(trades_df)
        avg_pnl = trades_df['pnl'].mean()
    else:
        win_rate = np.nan
        avg_pnl = np.nan

    # save outputs
    trades_csv = os.path.join(out_dir, 'trades_detail.csv')
    trades_df.to_csv(trades_csv, index=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    equity_series.plot(ax=ax)
    ax.set_title('Equity Curve - QQQ Backtest V1')
    ax.set_ylabel('Account Value')
    ax.grid(True)
    fig_path = os.path.join(out_dir, 'equity_curve.png')
    fig.savefig(fig_path)
    plt.close(fig)

    # print summary
    print('Backtest summary:')
    print(f'Initial capital: {initial_capital:,.2f}')
    print(f'Final equity: {equity_series.iloc[-1]:,.2f}')
    print(f'Total return: {total_return:.2%}')
    print(f'CAGR: {cagr:.2%}')
    print(f'Max drawdown: {md:.2%}')
    print(f'Number of trades: {len(trades_df)}')
    print(f'Win rate: {win_rate:.2%}')
    print(f'Average PnL per trade: {avg_pnl:,.2f}')
    print(f'Trades CSV: {trades_csv}')
    print(f'Equity plot: {fig_path}')

    return {
        'initial_capital': initial_capital,
        'final_equity': equity_series.iloc[-1],
        'total_return': total_return,
        'cagr': cagr,
        'max_drawdown': md,
        'n_trades': len(trades_df),
        'win_rate': win_rate,
        'equity_path': fig_path,
        'trades_csv': trades_csv,
    }


if __name__ == '__main__':
    res = run_backtest(initial_capital=100000.0, max_hold_days=5)
