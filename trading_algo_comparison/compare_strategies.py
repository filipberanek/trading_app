"""
Strategy Comparison

Runs all strategies on the same data and prints a side-by-side comparison table.
Also saves a combined bar-chart plot (CAGR + Max Drawdown).

Strategies:
  1. Buy the Dip         (trading_algo_buy_the_dip)
  2. Scale-in            (trading_algo_backtest_scalein)
  3. Scale-in + Hold     (trading_algo_backtest_scalein_hold)
  4. SMA Crossover       (trading_algo_sma_crossover)
  5. MACD                (trading_algo_macd_leverage)
  6. ATR-Adjusted SMA    (trading_algo_atr_sma)
  7. Dual Momentum       (trading_algo_dual_momentum)
  8. VIX Regime          (trading_algo_vix_regime)
  9. Volatility Targeting(trading_algo_vol_targeting)

Usage:
  python compare_strategies.py
  or call run_comparison() / run_grid_search_all() from another script.
"""

import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# make sibling folders importable
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_backtest_scalein'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_backtest_scalein_hold'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_sma_crossover'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_macd_leverage'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_buy_the_dip'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_atr_sma'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_dual_momentum'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_vix_regime'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_vol_targeting'))
sys.path.insert(0, os.path.join(ROOT, 'trading_algo_multi_asset'))

from backtest_scalein_simple import run_backtest_scalein
from backtest_scalein_hold import run_backtest_scalein_hold
from backtest_sma_crossover import run_backtest_sma_crossover
from backtest_macd_leverage import run_backtest_macd_leverage
from backtest_buy_the_dip import run_backtest_buy_the_dip
from backtest_atr_sma import run_backtest_atr_sma
from backtest_dual_momentum import run_backtest_dual_momentum
from backtest_vix_regime import run_backtest_vix_regime, fetch_vix
from backtest_vol_targeting import run_backtest_vol_targeting
from backtest_multi_asset import run_backtest_multi_asset, fetch_all as fetch_all_assets


def _pct(v):
    return f'{float(v):.2%}' if v is not None else 'N/A'


def _val(v):
    return str(v) if v is not None else 'N/A'


def fetch_data(ticker='QQQ', period='5y'):
    df = yf.download(ticker, period=period, progress=False)
    df = df.dropna()
    if getattr(df.columns, 'nlevels', 1) > 1:
        df.columns = df.columns.droplevel(1)
    return df


def run_comparison(ticker='QQQ', period='5y', initial_capital=10000.0,
                   buy_dip_params=None,
                   scalein_params=None,
                   scalein_hold_params=None,
                   sma_crossover_params=None,
                   macd_params=None,
                   atr_sma_params=None,
                   dual_momentum_params=None,
                   vix_regime_params=None,
                   vol_targeting_params=None,
                   multi_asset_params=None):
    """
    Runs all 10 strategies and prints a comparison table.
    Default params are research-informed best values.
    """
    if buy_dip_params is None:
        buy_dip_params = dict(drop_pct=0.05)
    if scalein_params is None:
        scalein_params = dict(bin_size_pct=0.02, max_drop_pct=0.2, initial_alloc_pct=0.3, exit_sma_window=30)
    if scalein_hold_params is None:
        scalein_hold_params = dict(hold_pct=0.5, bin_size_pct=0.02, max_drop_pct=0.2, initial_alloc_pct=0.3, exit_sma_window=30)
    if sma_crossover_params is None:
        sma_crossover_params = dict(sma_window=200, band_pct=0.01)
    if macd_params is None:
        macd_params = dict(ticker=ticker, fast_ema=12, slow_ema=26, signal_ema=9)
    if atr_sma_params is None:
        atr_sma_params = dict(sma_window=200, atr_window=20, atr_multiplier=1.0)
    if dual_momentum_params is None:
        dual_momentum_params = dict(lookback=126)
    if vix_regime_params is None:
        vix_regime_params = dict(vix_low=20, vix_high=30)
    if vol_targeting_params is None:
        vol_targeting_params = dict(target_vol=0.15, vol_window=20, max_leverage=1.0)
    if multi_asset_params is None:
        multi_asset_params = dict(lookback=126)

    print(f'Downloading data ({ticker}, {period})...')
    raw_df = fetch_data(ticker, period)
    raw_df.index = pd.to_datetime(raw_df.index)
    raw_df = raw_df[['Open', 'High', 'Low', 'Close', 'Volume']]
    if raw_df.empty:
        raise ValueError('No data returned.')

    print('Downloading VIX data...')
    raw_vix = fetch_vix(period)
    raw_vix.index = pd.to_datetime(raw_vix.index)

    print('Downloading multi-asset data (QQQ, TLT, GLD, SHY)...')
    raw_multi = fetch_all_assets(['QQQ', 'TLT', 'GLD', 'SHY'], period)

    print('Running Buy the Dip...')
    r0 = run_backtest_buy_the_dip(initial_capital=initial_capital, verbose=False, df=raw_df, **buy_dip_params)
    print('Running Scale-in...')
    r1 = run_backtest_scalein(initial_capital=initial_capital, verbose=False, df=raw_df, **scalein_params)
    print('Running Scale-in + Hold...')
    r2 = run_backtest_scalein_hold(initial_capital=initial_capital, verbose=False, df=raw_df, **scalein_hold_params)
    print('Running SMA Crossover...')
    r3 = run_backtest_sma_crossover(initial_capital=initial_capital, verbose=False, df=raw_df, alt_dfs=raw_multi, **sma_crossover_params)
    print('Running MACD...')
    macd_ticker = macd_params.pop('ticker', ticker)
    r4 = run_backtest_macd_leverage(ticker=macd_ticker, initial_capital=initial_capital, verbose=False, df=raw_df, **macd_params)
    macd_params['ticker'] = macd_ticker
    print('Running ATR-Adjusted SMA...')
    r5 = run_backtest_atr_sma(initial_capital=initial_capital, verbose=False, df=raw_df, alt_dfs=raw_multi, **atr_sma_params)
    print('Running Dual Momentum...')
    r6 = run_backtest_dual_momentum(initial_capital=initial_capital, verbose=False, dfs=raw_multi, **dual_momentum_params)
    print('Running VIX Regime...')
    r7 = run_backtest_vix_regime(initial_capital=initial_capital, verbose=False, df=raw_df, vix_df=raw_vix, **vix_regime_params)
    print('Running Volatility Targeting...')
    r8 = run_backtest_vol_targeting(initial_capital=initial_capital, verbose=False, df=raw_df, **vol_targeting_params)
    print('Running Multi-Asset Rotation...')
    r9 = run_backtest_multi_asset(initial_capital=initial_capital, verbose=False, dfs=raw_multi, **multi_asset_params)

    results = [r0, r1, r2, r3, r4, r5, r6, r7, r8, r9]
    names = ['BuyDip', 'Scale-in', 'S-in+Hld', 'SMACross', 'MACD', 'ATR-SMA', 'DualMom', 'VIX', 'VolTgt', 'MultiAsset']
    W = 10

    sep = '=' * (27 + len(names) * (W + 1))
    print('\n' + sep)
    header = f'{"":26}' + ''.join(f'{n:>{W}} ' for n in names)
    print(header)
    print(sep)

    def row(label, values):
        return f'{label:26}' + ''.join(f'{str(v):>{W}} ' for v in values)

    print(row('Final equity',     [f'{r["final_equity"]:,.0f}' for r in results]))
    print(row('Total return',     [f'{r["total_return"]:.1%}' for r in results]))
    print(row('CAGR',             [f'{r["cagr"]:.2%}' for r in results]))
    print(row('CAGR buy&hold',    [_pct(r.get('bh_cagr')) for r in results]))
    print(row('Max drawdown',     [f'{r["max_drawdown"]:.2%}' for r in results]))
    print(row('Win rate',         [_val(r.get('win_rate')) for r in results]))
    print(row('Trades closed',    [str(r['n_trades_closed']) for r in results]))
    print(row('Avg trade return', [_val(r.get('avg_trade_return')) for r in results]))
    print(row('Max trade gain',   [_val(r.get('max_trade_gain')) for r in results]))
    print(row('Max trade drop',   [_val(r.get('max_trade_drop')) for r in results]))
    print(sep)

    _plot_comparison(raw_df, results, names, ticker, initial_capital)
    return results


def _plot_comparison(raw_df, results, names, ticker, initial_capital):
    """Bar charts: CAGR and Max Drawdown for all strategies + buy&hold reference."""
    bh_cagr = next((r.get('bh_cagr') for r in results if r.get('bh_cagr') is not None), None)

    bh_close = raw_df['Close'].values
    bh_equity = pd.Series(initial_capital * bh_close / float(bh_close[0]), index=raw_df.index)
    roll_max = bh_equity.cummax()
    bh_dd = float(((bh_equity - roll_max) / roll_max).min())

    all_labels = ['Buy&Hold'] + names
    all_colors = ['gray', 'tab:purple', 'tab:blue', 'tab:orange', 'tab:green',
                  'tab:red', 'tab:cyan', 'tab:pink', 'tab:brown', 'tab:olive']
    all_cagrs = [bh_cagr] + [r['cagr'] for r in results]
    all_dds   = [bh_dd]   + [r['max_drawdown'] for r in results]

    x = range(len(all_labels))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 6))

    bars1 = ax1.bar(x, [v * 100 for v in all_cagrs], color=all_colors, edgecolor='white', linewidth=0.5)
    ax1.set_title(f'CAGR Comparison — {ticker}')
    ax1.set_ylabel('CAGR (%)')
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(all_labels, rotation=25, ha='right', fontsize=9)
    ax1.grid(axis='y', alpha=0.4)
    for bar, val in zip(bars1, all_cagrs):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                 f'{val:.1%}', ha='center', va='bottom', fontsize=8, fontweight='bold')

    bars2 = ax2.bar(x, [v * 100 for v in all_dds], color=all_colors, edgecolor='white', linewidth=0.5)
    ax2.set_title(f'Max Drawdown Comparison — {ticker}')
    ax2.set_ylabel('Max Drawdown (%)')
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(all_labels, rotation=25, ha='right', fontsize=9)
    ax2.grid(axis='y', alpha=0.4)
    for bar, val in zip(bars2, all_dds):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() - 0.3,
                 f'{val:.1%}', ha='center', va='top', fontsize=8, fontweight='bold')

    fig.tight_layout()
    out_dir = os.path.dirname(__file__)
    fig_path = os.path.join(out_dir, 'comparison_equity.png')
    fig.savefig(fig_path)
    plt.close(fig)
    print(f'\nComparison plot saved: {fig_path}')


def run_grid_search_all(ticker='QQQ', period='5y', initial_capital=10000.0, maximize='cagr'):
    """
    Runs grid search for all strategies and prints a final best-results comparison.
    """
    print('\n' + '=' * 60)
    print('GRID SEARCH — Buy the Dip')
    print('=' * 60)
    from backtest_buy_the_dip import grid_search as gs0
    df0 = gs0(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — Scale-in')
    print('=' * 60)
    from backtest_scalein_simple import grid_search as gs1
    df1 = gs1(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — Scale-in + Hold')
    print('=' * 60)
    from backtest_scalein_hold import grid_search as gs2
    df2 = gs2(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — SMA Crossover')
    print('=' * 60)
    from backtest_sma_crossover import grid_search as gs3
    df3 = gs3(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — MACD')
    print('=' * 60)
    from backtest_macd_leverage import grid_search as gs4
    df4 = gs4(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — ATR-Adjusted SMA')
    print('=' * 60)
    from backtest_atr_sma import grid_search as gs5
    df5 = gs5(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — Dual Momentum')
    print('=' * 60)
    from backtest_dual_momentum import grid_search as gs6
    df6 = gs6(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — VIX Regime')
    print('=' * 60)
    from backtest_vix_regime import grid_search as gs7
    df7 = gs7(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — Volatility Targeting')
    print('=' * 60)
    from backtest_vol_targeting import grid_search as gs8
    df8 = gs8(ticker=ticker, period=period, initial_capital=initial_capital, maximize=maximize)

    print('\n' + '=' * 60)
    print('GRID SEARCH — Multi-Asset Rotation')
    print('=' * 60)
    from backtest_multi_asset import grid_search as gs9
    df9 = gs9(period=period, initial_capital=initial_capital, maximize=maximize)

    # buy&hold CAGR reference
    try:
        raw_df = fetch_data(ticker, period)
        raw_df.index = pd.to_datetime(raw_df.index)
        years = (raw_df.index[-1] - raw_df.index[0]).days / 365.25
        bh_cagr = (float(raw_df['Close'].iloc[-1]) / float(raw_df['Close'].iloc[0])) ** (1 / years) - 1
        bh_cagr_str = f'{bh_cagr:.2%}'
    except Exception:
        bh_cagr_str = 'N/A'

    dfs = [df0, df1, df2, df3, df4, df5, df6, df7, df8, df9]
    col_names = ['BuyDip', 'Scale-in', 'S-in+Hld', 'SMACross', 'MACD', 'ATR-SMA', 'DualMom', 'VIX', 'VolTgt', 'MultiAsset']
    W = 10
    sep = '=' * (27 + len(col_names) * (W + 1))

    print('\n' + sep)
    print(f'BEST RESULTS (by {maximize})')
    print(sep)
    print(f'{"":26}' + ''.join(f'{n:>{W}} ' for n in col_names))
    print('-' * len(sep))
    print(f'{"bh_cagr (ref)":26}' + ''.join(f'{bh_cagr_str:>{W}} ' for _ in col_names))
    for key in ['cagr', 'total_return', 'max_drawdown', 'win_rate', 'n_trades']:
        vals = [str(df.iloc[0].get(key, 'N/A')) for df in dfs]
        print(f'{key:26}' + ''.join(f'{v:>{W}} ' for v in vals))
    print(sep)

    return dfs


if __name__ == '__main__':
    #run_comparison()
    run_grid_search_all()
