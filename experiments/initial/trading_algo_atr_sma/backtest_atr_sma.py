"""
Backtest QQQ - ATR-Adjusted SMA Crossover

Direct upgrade over fixed-band SMA crossover. The band widens automatically
during high-volatility periods (fewer whipsaws) and narrows during calm markets
(more responsive signals).

Entry: Close > SMA(sma_window) * (1 + ATR(atr_window)/Close * atr_multiplier)
Exit:  Close < SMA(sma_window) * (1 - ATR(atr_window)/Close * atr_multiplier)

When alt_dfs provided: on exit from QQQ, rotate to best of alt_assets (TLT/GLD)
by N-day momentum, or safe_asset (SHY) if all negative. Re-enter QQQ on entry signal.

Grid search: sma_window (100-250), atr_window (10-20), atr_multiplier (0.5-2.0)
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
from data_loader import load_ohlcv, load_all


DEFAULT_ALT_ASSETS   = ('TLT', 'GLD')
DEFAULT_SAFE_ASSET   = 'SHY'
DEFAULT_ALT_LOOKBACK = 63


def fetch_data(ticker='QQQ', period='5y'):
    return load_ohlcv(ticker, period=period)


def fetch_all(assets, period='5y'):
    """Load Open+Close for each asset. Returns dict {ticker: df}."""
    return load_all(list(assets), period=period)


def select_alt_asset(mom_row, alt_assets, safe_asset):
    """Pick best alt asset with positive momentum, else safe_asset."""
    alt_mom = {t: float(mom_row[t]) for t in alt_assets
               if t in mom_row.index and not pd.isna(mom_row[t])}
    if not alt_mom:
        return safe_asset
    best = max(alt_mom, key=alt_mom.get)
    return best if alt_mom[best] > 0 else safe_asset


def compute_atr(df, window):
    prev_close = df['Close'].shift(1)
    tr = pd.concat([
        df['High'] - df['Low'],
        (df['High'] - prev_close).abs(),
        (df['Low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


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
        qqq_trades = trades_df[trades_df['asset'] == 'QQQ'] if 'asset' in trades_df.columns else trades_df
        if len(qqq_trades) == 0:
            qqq_trades = trades_df
        win_rate = len(qqq_trades[qqq_trades['pnl'] > 0]) / len(qqq_trades)
        avg_pnl = qqq_trades['pnl'].mean()
        trade_returns = (qqq_trades['exit_price'] - qqq_trades['entry_price']) / qqq_trades['entry_price']
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


def print_stats(stats, initial_capital, equity_series, sma_window, atr_window, atr_multiplier, out_paths):
    print('ATR-Adjusted SMA backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'SMA window:               {sma_window}')
    print(f'ATR window:               {atr_window}')
    print(f'ATR multiplier:           {atr_multiplier}')
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


def save_plots(df, equity_series, invested_list, stats, sma_window, atr_window, atr_multiplier,
               out_dir, held_asset_list=None, all_assets=None):
    trades_df = stats['trades_df'].copy()
    if len(trades_df) > 0:
        trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
        trades_df['exit_date']  = pd.to_datetime(trades_df['exit_date'])

    invested_series = pd.Series(invested_list, index=equity_series.index)

    n_panels = 4 if held_asset_list is not None else 3
    height_ratios = [3, 2, 1, 1] if n_panels == 4 else [3, 2, 1]
    fig, axes = plt.subplots(n_panels, 1, sharex=True, figsize=(14, 4 * n_panels),
                             gridspec_kw={'height_ratios': height_ratios})
    ax_price, ax_equity, ax_inv = axes[0], axes[1], axes[2]

    df['Close'].plot(ax=ax_price, label='Close')
    df['SMA'].plot(ax=ax_price, label=f'SMA{sma_window}', linestyle='--', linewidth=1)
    df['upper_band'].plot(ax=ax_price, label='Upper band', linestyle=':', color='green', alpha=0.7)
    df['lower_band'].plot(ax=ax_price, label='Lower band', linestyle=':', color='red', alpha=0.7)
    if len(trades_df) > 0:
        qqq_trades = trades_df[trades_df['asset'] == 'QQQ'] if 'asset' in trades_df.columns else trades_df
        if len(qqq_trades) > 0:
            ax_price.scatter(qqq_trades['entry_date'], qqq_trades['entry_price'],
                             marker='^', color='green', label='Entry QQQ', zorder=5)
            ax_price.scatter(qqq_trades['exit_date'], qqq_trades['exit_price'],
                             marker='v', color='red', label='Exit QQQ', zorder=5)
    ax_price.set_title(f'ATR-Adjusted SMA Crossover (SMA{sma_window}, ATR{atr_window}×{atr_multiplier})')
    ax_price.set_ylabel('Price')
    ax_price.legend()
    ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    ax_inv.fill_between(invested_series.index, invested_series.values * 100,
                        step='post', alpha=0.4, color='steelblue', label='QQQ Invested %')
    ax_inv.set_ylabel('Invested %')
    ax_inv.set_ylim(0, 105)
    ax_inv.grid(True)
    ax_inv.legend()

    if held_asset_list is not None and all_assets is not None:
        ax_held = axes[3]
        asset_codes = {a: i for i, a in enumerate(all_assets)}
        held_series = pd.Series(held_asset_list, index=equity_series.index)
        held_numeric = held_series.map(asset_codes).fillna(-1)
        held_numeric.plot(ax=ax_held, drawstyle='steps-post', color='purple', linewidth=1)
        ax_held.set_yticks(list(asset_codes.values()))
        ax_held.set_yticklabels(list(asset_codes.keys()), fontsize=8)
        ax_held.set_ylabel('Held asset')
        ax_held.grid(True)

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_atr_sma.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


def run_backtest_atr_sma(ticker='QQQ', period='5y', initial_capital=10000.0,
                          sma_window=200, atr_window=20, atr_multiplier=1.0,
                          alt_assets=DEFAULT_ALT_ASSETS,
                          safe_asset=DEFAULT_SAFE_ASSET,
                          alt_lookback=DEFAULT_ALT_LOOKBACK,
                          verbose=True, df=None, alt_dfs=None):
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    use_alt = alt_dfs is not None

    if use_alt:
        alt_all    = list(alt_assets) + [safe_asset]
        alt_closes = pd.DataFrame({t: alt_dfs[t]['Close'] for t in alt_all if t in alt_dfs})
        alt_opens  = pd.DataFrame({t: alt_dfs[t]['Open']  for t in alt_all if t in alt_dfs})
        common     = df.index.intersection(alt_closes.dropna().index)
        df         = df.loc[common].copy()
        alt_closes = alt_closes.loc[common]
        alt_opens  = alt_opens.loc[common]
        alt_momentum = alt_closes / alt_closes.shift(alt_lookback) - 1

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

        alt_val   = (alt_shares * float(alt_closes[alt_asset].iat[i])
                     if use_alt and alt_asset is not None else 0.0)
        pos_value = shares * close
        eq        = cash + pos_value + alt_val
        equity_list.append(eq)
        equity_dates.append(date)
        invested_list.append(pos_value / eq if eq > 0 else 0.0)
        held_asset_list.append(
            ticker if in_position
            else (alt_asset if use_alt and alt_asset else 'CASH')
        )

        if i < warmup:
            continue
        sma_val  = df['SMA'].iat[i]
        band_val = df['band'].iat[i]
        if pd.isna(sma_val) or pd.isna(band_val):
            continue
        sma_f, band_f = float(sma_val), float(band_val)

        # Exit QQQ
        if in_position and close < sma_f * (1 - band_f):
            proceeds = shares * close
            pnl      = proceeds - shares * entry_price
            closed_trades.append({
                'asset': ticker,
                'entry_date': entry_date, 'entry_price': entry_price,
                'exit_date': date,        'exit_price': close,
                'shares': shares, 'pnl': pnl, 'held_days': i - (entry_idx or i),
            })
            cash       += proceeds
            shares      = 0.0
            in_position = False
            entry_price = entry_date = entry_idx = None

            # Rotate into alt when data available
            if use_alt and i + 1 < len(df) and not alt_momentum.iloc[i].isna().all():
                target        = select_alt_asset(alt_momentum.iloc[i], alt_assets, safe_asset)
                next_open_alt = float(alt_opens[target].iat[i + 1])
                alt_shares      = cash / next_open_alt
                cash           -= alt_shares * next_open_alt
                alt_asset       = target
                alt_entry_price = next_open_alt
                alt_entry_date  = df.index[i + 1]
                alt_entry_idx   = i + 1

        # Entry QQQ (sell alt first if held)
        if not in_position and close > sma_f * (1 + band_f):
            if i + 1 < len(df):
                next_open = float(df['Open'].iat[i + 1])
                next_date = df.index[i + 1]

                if use_alt and alt_asset is not None and alt_shares > 0:
                    exit_alt_px  = float(alt_opens[alt_asset].iat[i + 1])
                    alt_proceeds = alt_shares * exit_alt_px
                    alt_pnl      = alt_proceeds - alt_shares * alt_entry_price
                    closed_trades.append({
                        'asset': alt_asset,
                        'entry_date': alt_entry_date, 'entry_price': alt_entry_price,
                        'exit_date': next_date,        'exit_price': exit_alt_px,
                        'shares': alt_shares, 'pnl': alt_pnl,
                        'held_days': i + 1 - (alt_entry_idx or i + 1),
                    })
                    cash       += alt_proceeds
                    alt_shares  = 0.0
                    alt_asset   = None
                    alt_entry_price = alt_entry_date = alt_entry_idx = None

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
        trades_csv = os.path.join(out_dir, 'trades_detail_atr_sma.csv')
        stats['trades_df'].to_csv(trades_csv, index=False)
        all_assets_plot = ([ticker] + list(alt_assets) + [safe_asset]) if use_alt else None
        fig_path = save_plots(df, equity_series, invested_list, stats,
                              sma_window, atr_window, atr_multiplier, out_dir,
                              held_asset_list=held_asset_list if use_alt else None,
                              all_assets=all_assets_plot)
        print_stats(stats, initial_capital, equity_series, sma_window, atr_window, atr_multiplier,
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
                sma_window_values=(100, 150, 200, 250),
                atr_window_values=(10, 14, 20),
                atr_multiplier_values=(0.5, 1.0, 1.5, 2.0),
                alt_assets=DEFAULT_ALT_ASSETS,
                safe_asset=DEFAULT_SAFE_ASSET,
                alt_lookback=DEFAULT_ALT_LOOKBACK,
                maximize='cagr'):
    combos = list(itertools.product(sma_window_values, atr_window_values, atr_multiplier_values))
    print(f'Grid search: {len(combos)} combinations...')
    print('Downloading QQQ data once...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if raw_df.empty:
        raise ValueError('No data returned.')

    print('Downloading alt asset data (TLT, GLD, SHY)...')
    raw_alt_dfs = fetch_all(list(alt_assets) + [safe_asset], period)

    results = []
    for sma_w, atr_w, atr_m in combos:
        try:
            res = run_backtest_atr_sma(
                initial_capital=initial_capital,
                sma_window=sma_w, atr_window=atr_w, atr_multiplier=atr_m,
                alt_assets=alt_assets, safe_asset=safe_asset, alt_lookback=alt_lookback,
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

    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nFull results saved to: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best parameters (by {maximize}) ---')
    print(f'  sma_window={int(best["sma_window"])}, atr_window={int(best["atr_window"])}, '
          f'atr_multiplier={best["atr_multiplier"]}')
    print('Running full backtest with best parameters...\n')
    run_backtest_atr_sma(
        initial_capital=initial_capital,
        sma_window=int(best['sma_window']),
        atr_window=int(best['atr_window']),
        atr_multiplier=best['atr_multiplier'],
        alt_assets=alt_assets, safe_asset=safe_asset, alt_lookback=alt_lookback,
        verbose=True, df=raw_df, alt_dfs=raw_alt_dfs,
    )
    return results_df


if __name__ == '__main__':
    res = run_backtest_atr_sma(initial_capital=10000.0, sma_window=200, atr_window=20, atr_multiplier=1.0)
    print('\nRESULT:', res)
