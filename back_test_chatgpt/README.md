Backtest: QQQ - Version 1

Summary
-------
This folder contains a simple backtest for a Version 1 swing mean-reversion system trading QQQ.

Rules (detailed in the script)
- Instrument: QQQ (ETF)
- Data: daily, last 5 years (downloaded with yfinance)
- Entry: when Close[t] > SMA200[t] and 3-day return <= -3% (buy next day's Open)
- Exit (Version 1): Exit B — close >= SMA5 AND close > entry_open (ensures trade is profitable). A maximum hold (`MAX_HOLD_DAYS`) is applied (default 5 days) to avoid indefinite holds.
- Position sizing: position sized such that if the trade reaches the target price (SMA5 at entry day), the profit equals 1% of account. No leverage used. If target<=entry price, the signal is skipped.

Files
- `backtest_qqq_v1.py` — backtest script, produces `equity_curve.png` and prints metrics including max drawdown and total return.
