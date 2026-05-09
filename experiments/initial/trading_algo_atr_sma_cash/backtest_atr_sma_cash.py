"""
Backtest EQQQ - ATR-SMA with Cash Option

Upgrade over ATR-SMA: instead of always rotating into the "least bad" alt asset,
the strategy can hold plain cash (earning a configurable annual rate, default 2%)
when all alt assets have negative momentum.

Three possible states:
  1. Long EQQQ       — close > SMA * (1 + ATR/Close * multiplier)
  2. Long best alt   — EQQQ signal off AND best alt momentum > 0
  3. Cash @ rate     — EQQQ signal off AND all alts momentum <= 0

Cash earns `cash_rate_annual` (default 2% p.a.) compounded daily.

Entry/exit signals identical to ATR-SMA:
  Entry EQQQ : Close > SMA(sma_window) * (1 + ATR(atr_window)/Close * atr_multiplier)
  Exit EQQQ  : Close < SMA(sma_window) * (1 - ATR(atr_window)/Close * atr_multiplier)

Grid search: sma_window (100-250), atr_window (10-20), atr_multiplier (0.5-2.0)
"""

import os
import itertools
import pandas as pd
import numpy as np
import sys
import matplotlib.pyplot as plt

_ALGO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ALGO_ROOT not in sys.path:
    sys.path.insert(0, _ALGO_ROOT)
from data_loader import load_ohlcv, load_all

DEFAULT_ALT_ASSETS   = ('TLT', 'GLD')
DEFAULT_ALT_LOOKBACK = 63
CASH_LABEL           = 'CASH'


def fetch_data(ticker='QQQ', period='5y'):
    return load_ohlcv(ticker, period=period)


def fetch_all(assets, period='5y'):
    return load_all(list(assets), period=period)


def select_alt_asset_or_cash(strength_row, alt_assets):
    """Return alt with strongest uptrend (Close-SMA)/ATR > 0, or None (= cash)."""
    scores = {t: float(strength_row[t]) for t in alt_assets
              if t in strength_row.index and not pd.isna(strength_row[t])}
    if not scores:
        return None
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def compute_atr(df, window):
    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low']  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def compute_stats(equity_series, initial_capital, closed_trades, df=None):
    trades_df    = pd.DataFrame(closed_trades)
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years        = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr         = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    bh_cagr      = ((float(df['Close'].iloc[-1]) / float(df['Close'].iloc[0])) ** (1 / years) - 1
                    if df is not None and years > 0 else np.nan)
    md           = max_drawdown(equity_series)

    if len(trades_df) > 0 and 'pnl' in trades_df.columns:
        qqq_trades = (trades_df[trades_df['asset'] == 'QQQ']
                      if 'asset' in trades_df.columns else trades_df)
        if len(qqq_trades) == 0:
            qqq_trades = trades_df
        win_rate         = len(qqq_trades[qqq_trades['pnl'] > 0]) / len(qqq_trades)
        avg_pnl          = qqq_trades['pnl'].mean()
        tr_ret           = (qqq_trades['exit_price'] - qqq_trades['entry_price']) / qqq_trades['entry_price']
        avg_trade_return = tr_ret.mean()
        max_trade_gain   = tr_ret.max()
        max_trade_drop   = tr_ret.min()
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


def print_stats(stats, initial_capital, equity_series,
                sma_window, atr_window, atr_multiplier, cash_rate_annual, out_paths):
    print('ATR-SMA (cash-incl) backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'SMA window:               {sma_window}')
    print(f'ATR window:               {atr_window}')
    print(f'ATR multiplier:           {atr_multiplier}')
    print(f'Cash rate (p.a.):         {cash_rate_annual:.0%}')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    if not pd.isna(stats['bh_cagr']):
        print(f'CAGR buy & hold:          {stats["bh_cagr"]:.2%}')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Number of trades:         {stats["n_trades_closed"]}')
    if not pd.isna(stats['win_rate']):
        print(f'Win rate (EQQQ):          {stats["win_rate"]:.2%}')
        print(f'Average return per trade: {stats["avg_trade_return"]:.2%}')
        print(f'Max gain per trade:       {stats["max_trade_gain"]:.2%}')
        print(f'Max drop per trade:       {stats["max_trade_drop"]:.2%}')
    print(f'Trades CSV:               {out_paths["trades_csv"]}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots(df, equity_series, invested_list, held_asset_list,
               stats, sma_window, atr_window, atr_multiplier, out_dir):
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date']  = pd.to_datetime(trades_df['exit_date'])

    invested_series = pd.Series(invested_list, index=equity_series.index)
    held_series     = pd.Series(held_asset_list, index=equity_series.index)

    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(14, 16),
                              gridspec_kw={'height_ratios': [3, 2, 1, 1]})
    ax_price, ax_equity, ax_inv, ax_held = axes

    df['Close'].plot(ax=ax_price, label='Close')
    df['SMA'].plot(ax=ax_price, label=f'SMA{sma_window}', linestyle='--', linewidth=1)
    df['upper_band'].plot(ax=ax_price, label='Upper band', linestyle=':', color='green', alpha=0.7)
    df['lower_band'].plot(ax=ax_price, label='Lower band', linestyle=':', color='red', alpha=0.7)
    if len(trades_df) > 0:
        qqq_t = trades_df[trades_df['asset'] == 'QQQ'] if 'asset' in trades_df.columns else trades_df
        if len(qqq_t) > 0:
            ax_price.scatter(qqq_t['entry_date'], qqq_t['entry_price'],
                             marker='^', color='green', label='Entry EQQQ', zorder=5)
            ax_price.scatter(qqq_t['exit_date'], qqq_t['exit_price'],
                             marker='v', color='red', label='Exit EQQQ', zorder=5)
    ax_price.set_title(f'ATR-SMA cash-incl (SMA{sma_window}, ATR{atr_window}×{atr_multiplier})')
    ax_price.set_ylabel('Price')
    ax_price.legend(); ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value'); ax_equity.grid(True)

    (invested_series * 100).plot(ax=ax_inv, color='steelblue', label='EQQQ Invested %')
    ax_inv.set_ylabel('EQQQ %'); ax_inv.set_ylim(0, 105)
    ax_inv.grid(True); ax_inv.legend()

    all_states = ['EQQQ'] + [s for s in held_series.unique() if s not in ('EQQQ', CASH_LABEL)] + [CASH_LABEL]
    state_codes = {s: i for i, s in enumerate(all_states)}
    held_series.map(lambda s: state_codes.get(s, -1)).plot(
        ax=ax_held, drawstyle='steps-post', color='purple', linewidth=1)
    ax_held.set_yticks(list(state_codes.values()))
    ax_held.set_yticklabels(list(state_codes.keys()), fontsize=8)
    ax_held.set_ylabel('State'); ax_held.grid(True)

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_atr_sma_cash.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


# ── Core backtest ─────────────────────────────────────────────────────────────

def run_backtest_atr_sma_cash(ticker='QQQ', period='5y', initial_capital=10000.0,
                               sma_window=200, atr_window=20, atr_multiplier=1.0,
                               alt_assets=DEFAULT_ALT_ASSETS,
                               alt_lookback=DEFAULT_ALT_LOOKBACK,
                               cash_rate_annual=0.02,
                               commission=2.0,
                               verbose=True, df=None, alt_dfs=None):
    COMMISSION = commission
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    daily_cash_rate = (1 + cash_rate_annual) ** (1 / 252) - 1

    use_alt = alt_dfs is not None
    if use_alt:
        alt_closes  = pd.DataFrame({t: alt_dfs[t]['Close'] for t in alt_assets if t in alt_dfs})
        alt_opens   = pd.DataFrame({t: alt_dfs[t]['Open']  for t in alt_assets if t in alt_dfs})
        common      = df.index.intersection(alt_closes.dropna().index)
        df          = df.loc[common].copy()
        alt_closes  = alt_closes.loc[common]
        alt_opens   = alt_opens.loc[common]
        alt_sma      = alt_closes.rolling(sma_window).mean()
        alt_atr_df   = pd.DataFrame(
            {t: compute_atr(alt_dfs[t].loc[common], atr_window)
             for t in alt_assets if t in alt_dfs},
            index=common,
        )
        # Trend strength: (Close - SMA) / ATR — same logic as main signal
        # Positive = above SMA, higher = stronger uptrend
        alt_strength = (alt_closes - alt_sma) / alt_atr_df.replace(0, float('nan'))

    df['SMA']        = df['Close'].rolling(sma_window).mean()
    df['ATR']        = compute_atr(df, atr_window)
    df['band']       = df['ATR'] / df['Close'] * atr_multiplier
    df['upper_band'] = df['SMA'] * (1 + df['band'])
    df['lower_band'] = df['SMA'] * (1 - df['band'])

    warmup = max(sma_window, atr_window)

    cash        = float(initial_capital)
    shares      = 0.0
    in_position = False
    entry_price = entry_date = entry_idx = None

    alt_asset       = None
    alt_shares      = 0.0
    alt_entry_price = None
    alt_entry_date  = None
    alt_entry_idx   = None

    equity_list     = []
    equity_dates    = []
    invested_list   = []
    held_asset_list = []
    closed_trades   = []

    for i in range(len(df)):
        date  = df.index[i]
        close = float(df['Close'].iat[i])

        # Compound cash when sitting idle (not in EQQQ, not in alt)
        if not in_position and alt_asset is None:
            cash *= (1 + daily_cash_rate)

        alt_val   = (alt_shares * float(alt_closes[alt_asset].iat[i])
                     if use_alt and alt_asset is not None else 0.0)
        pos_value = shares * close
        eq        = cash + pos_value + alt_val
        equity_list.append(eq)
        equity_dates.append(date)
        invested_list.append(pos_value / eq if eq > 0 else 0.0)
        held_asset_list.append(
            ticker if in_position
            else (alt_asset if alt_asset else CASH_LABEL)
        )

        if i < warmup:
            continue
        sma_val  = df['SMA'].iat[i]
        band_val = df['band'].iat[i]
        if pd.isna(sma_val) or pd.isna(band_val):
            continue
        sma_f, band_f = float(sma_val), float(band_val)

        # ── Exit EQQQ ────────────────────────────────────────────────────────
        if in_position and close < sma_f * (1 - band_f):
            if i + 1 < len(df):
                exit_px       = float(df['Open'].iat[i + 1])
                exit_date_val = df.index[i + 1]
            else:
                exit_px       = close          # last bar — no next open
                exit_date_val = date
            proceeds = shares * exit_px - COMMISSION
            pnl      = proceeds - shares * entry_price
            closed_trades.append({
                'asset': ticker,
                'entry_date': entry_date, 'entry_price': entry_price,
                'exit_date': exit_date_val, 'exit_price': exit_px,
                'shares': shares, 'pnl': pnl, 'held_days': i - (entry_idx or i),
            })
            cash       += proceeds
            shares      = 0.0
            in_position = False
            entry_price = entry_date = entry_idx = None

            # Decide: rotate into best alt or go to cash
            if use_alt and i + 1 < len(df) and not alt_strength.iloc[i].isna().all():
                target = select_alt_asset_or_cash(alt_strength.iloc[i], alt_assets)
                if target is not None:
                    next_open_alt   = float(alt_opens[target].iat[i + 1])
                    cash           -= COMMISSION
                    alt_shares      = cash / next_open_alt
                    cash           -= alt_shares * next_open_alt
                    alt_asset       = target
                    alt_entry_price = next_open_alt
                    alt_entry_date  = df.index[i + 1]
                    alt_entry_idx   = i + 1
                # else: target is None → stay in cash (no action needed)

        # ── Entry EQQQ ───────────────────────────────────────────────────────
        if not in_position and close > sma_f * (1 + band_f):
            if i + 1 < len(df):
                next_open = float(df['Open'].iat[i + 1])
                next_date = df.index[i + 1]

                # Close alt position first if held
                if use_alt and alt_asset is not None and alt_shares > 0:
                    exit_alt_px  = float(alt_opens[alt_asset].iat[i + 1])
                    alt_proceeds = alt_shares * exit_alt_px - COMMISSION
                    alt_pnl      = alt_proceeds - alt_shares * alt_entry_price
                    closed_trades.append({
                        'asset': alt_asset,
                        'entry_date': alt_entry_date, 'entry_price': alt_entry_price,
                        'exit_date': next_date,        'exit_price': exit_alt_px,
                        'shares': alt_shares, 'pnl': alt_pnl,
                        'held_days': i + 1 - (alt_entry_idx or i + 1),
                    })
                    cash      += alt_proceeds
                    alt_shares = 0.0
                    alt_asset  = None
                    alt_entry_price = alt_entry_date = alt_entry_idx = None

                # Buy EQQQ
                cash       -= COMMISSION
                shares      = cash / next_open
                cash       -= shares * next_open
                in_position = True
                entry_price = next_open
                entry_date  = next_date
                entry_idx   = i + 1

    equity_series = pd.Series(equity_list, index=equity_dates)
    stats = compute_stats(equity_series, initial_capital, closed_trades, df=df)

    trades_csv = fig_path = None
    if verbose:
        trades_csv = os.path.join(out_dir, 'trades_detail_atr_sma_cash.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        fig_path = save_plots(df, equity_series, invested_list, held_asset_list,
                               stats, sma_window, atr_window, atr_multiplier, out_dir)
        print_stats(stats, initial_capital, equity_series, sma_window, atr_window,
                    atr_multiplier, cash_rate_annual, {'trades_csv': trades_csv, 'fig_path': fig_path})

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


# ── Grid search ───────────────────────────────────────────────────────────────

def grid_search(ticker='QQQ', period='5y', initial_capital=10000.0,
                sma_window_values=(100, 150, 200, 250),
                atr_window_values=(10, 14, 20),
                atr_multiplier_values=(0.5, 1.0, 1.5, 2.0),
                alt_assets=DEFAULT_ALT_ASSETS,
                alt_lookback=DEFAULT_ALT_LOOKBACK,
                cash_rate_annual=0.02,
                maximize='cagr'):
    combos = list(itertools.product(sma_window_values, atr_window_values, atr_multiplier_values))
    print(f'Grid search: {len(combos)} combinations...')
    print('Downloading EQQQ data once...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if raw_df.empty:
        raise ValueError('No data returned.')

    print('Downloading alt asset data...')
    raw_alt_dfs = fetch_all(list(alt_assets), period)

    results = []
    for sma_w, atr_w, atr_m in combos:
        try:
            res = run_backtest_atr_sma_cash(
                initial_capital=initial_capital,
                sma_window=sma_w, atr_window=atr_w, atr_multiplier=atr_m,
                alt_assets=alt_assets, alt_lookback=alt_lookback,
                cash_rate_annual=cash_rate_annual,
                verbose=False, df=raw_df, alt_dfs=raw_alt_dfs,
            )
            results.append({
                'sma_window': sma_w, 'atr_window': atr_w, 'atr_multiplier': atr_m,
                'cagr': res['cagr'], 'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'], 'win_rate': res['win_rate'],
                'n_trades': res['n_trades_closed'],
            })
        except Exception as e:
            print(f'  ERROR sma={sma_w},atr={atr_w},mult={atr_m}: {e}')

    results_df = pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)
    print(f'\nTop 10 by {maximize}:')
    print(results_df.head(10).to_string(index=False))

    out_dir  = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nResults saved: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best (by {maximize}) ---')
    print(f'  sma={int(best["sma_window"])}, atr={int(best["atr_window"])}, mult={best["atr_multiplier"]}')
    print('Running full backtest with best parameters...\n')
    run_backtest_atr_sma_cash(
        initial_capital=initial_capital,
        sma_window=int(best['sma_window']),
        atr_window=int(best['atr_window']),
        atr_multiplier=best['atr_multiplier'],
        alt_assets=alt_assets, alt_lookback=alt_lookback,
        cash_rate_annual=cash_rate_annual,
        verbose=True, df=raw_df, alt_dfs=raw_alt_dfs,
    )
    return results_df


if __name__ == '__main__':
    _TICKER    = 'EQQQ'
    _ALT_ASSETS = ('IUES', 'IGLN', 'IBZL', 'EEA', 'IUCS', 'SEGA')

    _main_df  = load_ohlcv(_TICKER, period='all')
    _alt_dfs  = {}
    for _t in _ALT_ASSETS:
        try:
            _alt_dfs[_t] = load_ohlcv(_t, period='all')
        except ValueError as _e:
            print(f'WARNING: {_e}')

    # Rotace do alt assetů + cash fallback:
    res = run_backtest_atr_sma_cash(
         ticker=_TICKER, initial_capital=10_000.0,
         sma_window=30, atr_window=10, atr_multiplier=0.3,
         alt_assets=_ALT_ASSETS,
         df=_main_df, alt_dfs=_alt_dfs,
         verbose=True,
    )

    # Jen cash při výstupu z EQQQ (žádná rotace):
    """
    res = run_backtest_atr_sma_cash(
        ticker=_TICKER, initial_capital=10_000.0,
        sma_window=30, atr_window=10, atr_multiplier=0.3,
        alt_assets=(),
        df=_main_df,
        verbose=True,
    )
    """
    print('\nRESULT:', res)
