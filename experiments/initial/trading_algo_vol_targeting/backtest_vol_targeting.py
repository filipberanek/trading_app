"""
Backtest QQQ - Volatility Targeting

Continuously sizes the position to maintain a target annualized volatility.
No binary in/out — position scales from 0% to 100% (or up to max_leverage).

position_size[t] = min(target_vol / realized_vol[t-1], max_leverage)

Where realized_vol = rolling std of daily returns * sqrt(252).

Position determined at end of day t-1 and applied on day t.
No rebalancing cost modeled (assumes liquid ETF).

Grid search: target_vol (0.10-0.25), vol_window (10-60), max_leverage (1.0-1.5)
"""

import os
import sys
import itertools
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

_ALGO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ALGO_ROOT not in sys.path:
    sys.path.insert(0, _ALGO_ROOT)
from data_loader import load_ohlcv


def fetch_data(ticker='QQQ', period='5y'):
    return load_ohlcv(ticker, period=period)


def max_drawdown(equity):
    roll_max = equity.cummax()
    return ((equity - roll_max) / roll_max).min()


def compute_stats(equity_series, initial_capital, df=None):
    total_return = equity_series.iloc[-1] / initial_capital - 1.0
    years = (equity_series.index[-1] - equity_series.index[0]).days / 365.25
    cagr = (equity_series.iloc[-1] / initial_capital) ** (1 / years) - 1 if years > 0 else np.nan
    if df is not None and years > 0:
        bh_cagr = (float(df['Close'].iloc[-1]) / float(df['Close'].iloc[0])) ** (1 / years) - 1
    else:
        bh_cagr = np.nan
    md = max_drawdown(equity_series)
    return {
        'total_return': total_return, 'cagr': cagr, 'bh_cagr': bh_cagr,
        'max_drawdown': md,
    }


def print_stats(stats, initial_capital, equity_series, target_vol, vol_window, max_leverage, out_paths):
    print('Volatility Targeting backtest summary:')
    print(f'Initial capital:          {initial_capital:,.2f}')
    print(f'Target volatility:        {target_vol:.0%}')
    print(f'Vol window:               {vol_window} days')
    print(f'Max leverage:             {max_leverage:.1f}x')
    print(f'Final equity:             {equity_series.iloc[-1]:,.2f}')
    print(f'Total return:             {stats["total_return"]:.2%}')
    print(f'CAGR:                     {stats["cagr"]:.2%}')
    print(f'CAGR buy & hold:          {stats["bh_cagr"]:.2%}' if not pd.isna(stats['bh_cagr']) else 'CAGR buy & hold:          N/A')
    print(f'Max drawdown:             {stats["max_drawdown"]:.2%}')
    print(f'Plot:                     {out_paths["fig_path"]}')


def save_plots(df, equity_series, pos_size_series, realized_vol_series,
               target_vol, vol_window, max_leverage, out_dir):
    fig, axes = plt.subplots(4, 1, sharex=True, figsize=(14, 14),
                              gridspec_kw={'height_ratios': [3, 2, 1, 1]})
    ax_price, ax_equity, ax_pos, ax_vol = axes

    df['Close'].plot(ax=ax_price, label='Close')
    ax_price.set_title(f'Volatility Targeting (target={target_vol:.0%}, window={vol_window}d, max_lev={max_leverage}x)')
    ax_price.set_ylabel('Price')
    ax_price.legend()
    ax_price.grid(True)

    equity_series.plot(ax=ax_equity, color='steelblue')
    ax_equity.set_title('Equity Curve')
    ax_equity.set_ylabel('Account Value')
    ax_equity.grid(True)

    (pos_size_series * 100).plot(ax=ax_pos, color='purple', label='Position size %')
    ax_pos.set_ylabel('Position %')
    ax_pos.set_ylim(0, max_leverage * 100 + 5)
    ax_pos.grid(True)
    ax_pos.legend()

    (realized_vol_series * 100).plot(ax=ax_vol, color='darkorange', label='Realized vol (annualized %)')
    ax_vol.axhline(target_vol * 100, color='red', linestyle='--', linewidth=1, label=f'Target {target_vol:.0%}')
    ax_vol.set_ylabel('Volatility %')
    ax_vol.grid(True)
    ax_vol.legend()

    fig.tight_layout()
    out_fig = os.path.join(out_dir, 'backtest_vol_targeting.png')
    fig.savefig(out_fig)
    plt.close(fig)
    return out_fig


def run_backtest_vol_targeting(ticker='QQQ', period='5y', initial_capital=10000.0,
                                target_vol=0.15, vol_window=20, max_leverage=1.0,
                                verbose=True, df=None):
    out_dir = os.path.dirname(__file__)
    if df is None:
        df = fetch_data(ticker, period)
        df.index = pd.to_datetime(df.index)
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if df.empty:
        raise ValueError('No data returned.')
    df = df.copy()

    returns = df['Close'].pct_change()
    realized_vol = returns.rolling(vol_window).std() * np.sqrt(252)

    # Position sized by previous day's volatility; clipped to [0, max_leverage]
    pos_size = (target_vol / realized_vol).clip(lower=0, upper=max_leverage)
    pos_size = pos_size.shift(1).fillna(0)  # use yesterday's vol for today's position
    pos_size = pos_size.fillna(0)

    strategy_returns = (pos_size * returns).fillna(0)
    equity_values = initial_capital * (1 + strategy_returns).cumprod()
    equity_series = pd.Series(equity_values.values, index=df.index)

    stats = compute_stats(equity_series, initial_capital, df=df)

    fig_path = None
    if verbose:
        fig_path = save_plots(df, equity_series, pos_size, realized_vol,
                               target_vol, vol_window, max_leverage, out_dir)
        print_stats(stats, initial_capital, equity_series, target_vol, vol_window,
                    max_leverage, {'fig_path': fig_path})

    def _f(v):
        return round(float(v), 3) if not pd.isna(v) else None

    return {
        'initial_capital': float(initial_capital),
        'final_equity': _f(equity_series.iloc[-1]),
        'total_return': _f(stats['total_return']),
        'cagr': _f(stats['cagr']),
        'bh_cagr': _f(stats['bh_cagr']),
        'max_drawdown': _f(stats['max_drawdown']),
        'n_trades_closed': 0,
        'win_rate': None,
        'avg_trade_return': None,
        'max_trade_gain': None,
        'max_trade_drop': None,
        'fig_path': fig_path,
        'trades_csv': None,
    }


def grid_search(ticker='QQQ', period='5y', initial_capital=10000.0,
                target_vol_values=(0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.3, 0.35, 0.4),
                vol_window_values=(2, 3, 5, 7, 10, 20, 30, 40, 60),
                max_leverage_values=(1.0,),
                maximize='cagr'):
    combos = list(itertools.product(target_vol_values, vol_window_values, max_leverage_values))
    print(f'Grid search: {len(combos)} combinations...')
    print('Downloading data once...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if raw_df.empty:
        raise ValueError('No data returned.')

    results = []
    for tv, vw, ml in combos:
        try:
            res = run_backtest_vol_targeting(
                initial_capital=initial_capital,
                target_vol=tv, vol_window=vw, max_leverage=ml,
                verbose=False, df=raw_df,
            )
            results.append({
                'target_vol': tv, 'vol_window': vw, 'max_leverage': ml,
                'cagr': res['cagr'], 'total_return': res['total_return'],
                'max_drawdown': res['max_drawdown'],
                'win_rate': None, 'n_trades': 0,
            })
        except Exception as e:
            print(f'  ERROR target_vol={tv},window={vw},leverage={ml}: {e}')

    results_df = pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)
    print(f'\nTop 10 by {maximize}:')
    print(results_df.head(10).to_string(index=False))

    out_dir = os.path.dirname(__file__)
    csv_path = os.path.join(out_dir, 'grid_search_results.csv')
    results_df.to_csv(csv_path, index=False)
    print(f'\nFull results saved to: {csv_path}')

    best = results_df.iloc[0]
    print(f'\n--- Best parameters (by {maximize}) ---')
    print(f'  target_vol={best["target_vol"]:.0%}, vol_window={int(best["vol_window"])}, '
          f'max_leverage={best["max_leverage"]}x')
    print('Running full backtest with best parameters...\n')
    run_backtest_vol_targeting(
        initial_capital=initial_capital,
        target_vol=best['target_vol'],
        vol_window=int(best['vol_window']),
        max_leverage=best['max_leverage'],
        verbose=True, df=raw_df,
    )
    return results_df


if __name__ == '__main__':
    #res = run_backtest_vol_targeting(initial_capital=10000.0, target_vol=0.15, vol_window=20)
    #print('\nRESULT:', res)
    grid_search()