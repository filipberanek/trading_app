"""
Strategy Comparison

Runs all strategies on the same data and prints a side-by-side comparison table.
Also saves a combined bar-chart plot (CAGR + Max Drawdown).

Base ticker : EQQQ (Invesco NASDAQ-100 UCITS)
Rotation    : EQQQ, SEGA, IUES, EWG2, IDTL, EEA, IBZL, IUCS
              (low positive-correlation selection from Xetra universe)
Data source : local CSVs from  data preprocessing/input_data/

Usage:
  python compare_strategies.py
  or call run_comparison() / run_grid_search_all() from another script.
"""

import os
import sys
from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
import yfinance as yf

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE  = os.path.dirname(__file__)                              # trading_algo_comparison/
ROOT   = os.path.dirname(_HERE)                                 # experiments/initial/
_APP   = os.path.dirname(os.path.dirname(ROOT))                 # trading_app/
DATA_DIR = os.path.join(_APP, 'data_preprocessing', 'input_data')

# ── Ticker config ─────────────────────────────────────────────────────────────

MAIN_TICKER  = 'EQQQ'

# Alternatives rotated into when EQQQ signal is off (SMA / ATR-SMA strategies)
ALT_ASSETS   = ('IUES', 'IGLN', 'IDTL', 'IBZL', 'EEA', 'IUCS')

# Safe-haven for all rotation strategies
SAFE_ASSET     = 'XEON'
SAFE_ASSET_ROT = SAFE_ASSET

# Full risky universe for momentum-rotation strategies (Dual Momentum, Multi-Asset)
RISKY_ASSETS = ('EQQQ', 'IUES', 'IGLN', 'IBZL', 'EEA', 'IUCS')

# All tickers needed for data loading
ALL_ROTATION = list(RISKY_ASSETS) + [SAFE_ASSET]

# ── Strategy imports ──────────────────────────────────────────────────────────

for _folder in ('trading_algo_backtest_scalein', 'trading_algo_backtest_scalein_hold',
                'trading_algo_sma_crossover', 'trading_algo_macd_leverage',
                'trading_algo_buy_the_dip', 'trading_algo_atr_sma',
                'trading_algo_dual_momentum', 'trading_algo_vix_regime',
                'trading_algo_vol_targeting', 'trading_algo_multi_asset'):
    sys.path.insert(0, os.path.join(ROOT, _folder))

from backtest_scalein_simple  import run_backtest_scalein
from backtest_scalein_hold    import run_backtest_scalein_hold
from backtest_sma_crossover   import run_backtest_sma_crossover
from backtest_macd_leverage   import run_backtest_macd_leverage
from backtest_buy_the_dip     import run_backtest_buy_the_dip
from backtest_atr_sma         import run_backtest_atr_sma
from backtest_dual_momentum   import run_backtest_dual_momentum
from backtest_vix_regime      import run_backtest_vix_regime, fetch_vix
from backtest_vol_targeting   import run_backtest_vol_targeting
from backtest_multi_asset     import run_backtest_multi_asset


# ── Data loading ──────────────────────────────────────────────────────────────

def load_local(ticker: str) -> pd.DataFrame:
    """Load OHLCV from local CSV (data preprocessing/input_data/<ticker>.csv)."""
    path = os.path.join(DATA_DIR, f'{ticker}.csv')
    if not os.path.exists(path):
        raise FileNotFoundError(f'Local CSV not found: {path}')
    df = pd.read_csv(path, parse_dates=['Date'], index_col='Date')
    df.index = pd.to_datetime(df.index)
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
    return df


def load_all_local(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Load multiple tickers from local CSVs; skips missing files with a warning."""
    result = {}
    for t in tickers:
        try:
            result[t] = load_local(t)
        except FileNotFoundError as e:
            print(f'  WARNING: {e}')
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pct(v):
    return f'{float(v):.2%}' if v is not None else 'N/A'


def _val(v):
    return str(v) if v is not None else 'N/A'


def _buy_and_hold_result(df: pd.DataFrame, initial_capital: float) -> dict:
    close  = df['Close']
    equity = initial_capital * close / float(close.iloc[0])
    years  = (equity.index[-1] - equity.index[0]).days / 365.25
    tr     = float(equity.iloc[-1]) / initial_capital - 1.0
    cagr   = (float(equity.iloc[-1]) / initial_capital) ** (1 / years) - 1 if years > 0 else None
    roll_max = equity.cummax()
    max_dd   = float(((equity - roll_max) / roll_max).min())
    return {
        'initial_capital': float(initial_capital),
        'final_equity': round(float(equity.iloc[-1]), 2),
        'total_return': round(tr, 3),
        'cagr': round(cagr, 3) if cagr is not None else None,
        'bh_cagr': None,
        'max_drawdown': round(max_dd, 3),
        'n_trades_closed': 0,
        'win_rate': None,
        'avg_trade_return': None,
        'max_trade_gain': None,
        'max_trade_drop': None,
    }


# ── Main comparison ───────────────────────────────────────────────────────────

def run_comparison(initial_capital: float = 10_000.0,
                   buy_dip_params: dict | None = None,
                   scalein_params: dict | None = None,
                   scalein_hold_params: dict | None = None,
                   sma_crossover_params: dict | None = None,
                   macd_params: dict | None = None,
                   atr_sma_params: dict | None = None,
                   dual_momentum_params: dict | None = None,
                   vix_regime_params: dict | None = None,
                   vol_targeting_params: dict | None = None,
                   multi_asset_params: dict | None = None):
    """
    Run all strategies and print a side-by-side comparison table.
    Data is loaded from local CSVs (no yfinance needed for EQQQ / rotation tickers).
    VIX is still downloaded from yfinance.
    """
    if buy_dip_params       is None: buy_dip_params       = dict(drop_pct=0.05)
    if scalein_params       is None: scalein_params       = dict(bin_size_pct=0.02, max_drop_pct=0.2, initial_alloc_pct=0.3, exit_sma_window=30)
    if scalein_hold_params  is None: scalein_hold_params  = dict(hold_pct=0.5, bin_size_pct=0.02, max_drop_pct=0.2, initial_alloc_pct=0.3, exit_sma_window=30)
    if sma_crossover_params is None: sma_crossover_params = dict(sma_window=200, band_pct=0.01)
    if macd_params          is None: macd_params          = dict(fast_ema=12, slow_ema=26, signal_ema=9)
    if atr_sma_params       is None: atr_sma_params       = dict(sma_window=200, atr_window=20, atr_multiplier=1.0)
    if dual_momentum_params is None: dual_momentum_params = dict(lookback=126)
    if vix_regime_params    is None: vix_regime_params    = dict(vix_low=20, vix_high=30)
    if vol_targeting_params is None: vol_targeting_params = dict(target_vol=0.15, vol_window=20, max_leverage=1.0)
    if multi_asset_params   is None: multi_asset_params   = dict(lookback=126)

    # ── Load data ─────────────────────────────────────────────────────────────
    print(f'Loading {MAIN_TICKER} from local CSV...')
    raw_df = load_local(MAIN_TICKER)

    print(f'Loading rotation tickers from local CSVs: {ALL_ROTATION}')
    raw_multi = load_all_local(ALL_ROTATION)

    print('Downloading VIX data from yfinance...')
    raw_vix = fetch_vix('max')
    raw_vix.index = pd.to_datetime(raw_vix.index)

    # Align VIX to the date range of EQQQ
    raw_vix = raw_vix.reindex(raw_df.index, method='ffill').dropna()

    # ── Run strategies ────────────────────────────────────────────────────────
    print('Running Buy the Dip...')
    r0 = run_backtest_buy_the_dip(
        initial_capital=initial_capital, verbose=False, df=raw_df, **buy_dip_params)

    print('Running Scale-in...')
    r1 = run_backtest_scalein(
        initial_capital=initial_capital, verbose=False, df=raw_df, **scalein_params)

    print('Running Scale-in + Hold...')
    r2 = run_backtest_scalein_hold(
        initial_capital=initial_capital, verbose=False, df=raw_df, **scalein_hold_params)

    print('Running SMA Crossover...')
    r3 = run_backtest_sma_crossover(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=raw_df, alt_dfs=raw_multi,
        alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET,
        **sma_crossover_params)

    print('Running MACD...')
    r4 = run_backtest_macd_leverage(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=raw_df, **macd_params)

    print('Running ATR-Adjusted SMA...')
    r5 = run_backtest_atr_sma(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=raw_df, alt_dfs=raw_multi,
        alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET,
        **atr_sma_params)

    print('Running Dual Momentum...')
    r6 = run_backtest_dual_momentum(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        dfs=raw_multi,
        risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET,
        **dual_momentum_params)

    print('Running VIX Regime...')
    r7 = run_backtest_vix_regime(
        initial_capital=initial_capital, verbose=False,
        df=raw_df, vix_df=raw_vix, **vix_regime_params)

    print('Running Volatility Targeting...')
    r8 = run_backtest_vol_targeting(
        initial_capital=initial_capital, verbose=False, df=raw_df, **vol_targeting_params)

    print('Running Multi-Asset Rotation...')
    r9 = run_backtest_multi_asset(
        initial_capital=initial_capital, verbose=False,
        dfs=raw_multi,
        risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET,
        **multi_asset_params)

    r_bh    = _buy_and_hold_result(raw_df, initial_capital)
    results = [r_bh, r0, r1, r2, r3, r4, r5, r6, r7, r8, r9]
    names   = ['Buy&Hold', 'BuyDip', 'Scale-in', 'S-in+Hld', 'SMACross', 'MACD',
               'ATR-SMA', 'DualMom', 'VIX', 'VolTgt', 'MultiAsset']
    W   = 10
    sep = '=' * (27 + len(names) * (W + 1))

    print(f'\n{sep}')
    print(f'{"":26}' + ''.join(f'{n:>{W}} ' for n in names))
    print(sep)

    def row(label, values):
        return f'{label:26}' + ''.join(f'{str(v):>{W}} ' for v in values)

    print(row('Final equity',     [f'{r["final_equity"]:,.0f}'  for r in results]))
    print(row('Total return',     [f'{r["total_return"]:.1%}'   for r in results]))
    print(row('CAGR',             [f'{r["cagr"]:.2%}'           for r in results]))
    print(row('Max drawdown',     [f'{r["max_drawdown"]:.2%}'   for r in results]))
    print(row('Win rate',         [_val(r.get('win_rate'))       for r in results]))
    print(row('Trades closed',    [str(r['n_trades_closed'])     for r in results]))
    print(row('Avg trade return', [_val(r.get('avg_trade_return')) for r in results]))
    print(row('Max trade gain',   [_val(r.get('max_trade_gain')) for r in results]))
    print(row('Max trade drop',   [_val(r.get('max_trade_drop')) for r in results]))
    print(sep)

    ts = datetime.now().strftime('%Y%m%d_%H%M')
    _plot_comparison(results, names, ts)
    _save_summary_txt(results, names, ts)
    return results


def _plot_comparison(results, names, ts: str):
    colors = ['gray', 'tab:purple', 'tab:blue', 'tab:orange', 'tab:green',
              'tab:red', 'tab:cyan', 'tab:pink', 'tab:brown', 'tab:olive', 'tab:gray']

    all_labels = names
    all_cagrs  = [r['cagr'] for r in results]
    all_dds    = [r['max_drawdown'] for r in results]
    all_trades = [r['n_trades_closed'] for r in results]

    x = list(range(len(all_labels)))
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(24, 7))
    fig.suptitle(f'Strategy Comparison — {MAIN_TICKER}  |  {ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:]}',
                 fontsize=13, fontweight='bold')

    def _annotate(ax, bars, vals, fmt, va='bottom', offset=0.1):
        for bar, val in zip(bars, vals):
            if val is None:
                continue
            y = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2,
                    y + offset if va == 'bottom' else y - offset,
                    fmt(val), ha='center', va=va, fontsize=8, fontweight='bold')

    # ── subplot 1: CAGR ───────────────────────────────────────────────────────
    bars1 = ax1.bar(x, [v * 100 if v is not None else 0 for v in all_cagrs],
                    color=colors, edgecolor='white', linewidth=0.5)
    ax1.set_title(f'CAGR  ({ts})')
    ax1.set_ylabel('CAGR (%)')
    ax1.set_xticks(x)
    ax1.set_xticklabels(all_labels, rotation=30, ha='right', fontsize=9)
    ax1.grid(axis='y', alpha=0.4)
    _annotate(ax1, bars1, all_cagrs, lambda v: f'{v:.1%}')

    # ── subplot 2: Max Drawdown ───────────────────────────────────────────────
    bars2 = ax2.bar(x, [v * 100 for v in all_dds],
                    color=colors, edgecolor='white', linewidth=0.5)
    ax2.set_title(f'Max Drawdown  ({ts})')
    ax2.set_ylabel('Max Drawdown (%)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(all_labels, rotation=30, ha='right', fontsize=9)
    ax2.grid(axis='y', alpha=0.4)
    _annotate(ax2, bars2, all_dds, lambda v: f'{v:.1%}', va='top', offset=0.3)

    # ── subplot 3: Number of trades ───────────────────────────────────────────
    bars3 = ax3.bar(x, all_trades, color=colors, edgecolor='white', linewidth=0.5)
    ax3.set_title(f'Closed Trades  ({ts})')
    ax3.set_ylabel('Number of trades')
    ax3.set_xticks(x)
    ax3.set_xticklabels(all_labels, rotation=30, ha='right', fontsize=9)
    ax3.grid(axis='y', alpha=0.4)
    _annotate(ax3, bars3, all_trades, lambda v: str(int(v)))

    fig.tight_layout()
    fig_path = os.path.join(_HERE, f'comparison_{ts}.png')
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)
    print(f'\nComparison plot saved: {fig_path}')


def _save_summary_txt(results, names, ts: str):
    W   = 12
    sep = '=' * (28 + len(names) * (W + 1))

    def row(label, vals):
        return f'{label:27}' + ''.join(f'{str(v):>{W}} ' for v in vals)

    lines = [
        f'Strategy comparison — {MAIN_TICKER}',
        f'Generated : {ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:]}',
        f'Rotation  : {", ".join(list(RISKY_ASSETS) + [SAFE_ASSET])}',
        '',
        sep,
        f'{"":27}' + ''.join(f'{n:>{W}} ' for n in names),
        sep,
        row('CAGR',             [f'{r["cagr"]:.2%}'          for r in results]),
        row('Total return',     [f'{r["total_return"]:.1%}'  for r in results]),
        row('Final equity',     [f'{r["final_equity"]:,.0f}' for r in results]),
        row('Max drawdown',     [f'{r["max_drawdown"]:.2%}'  for r in results]),
        row('Win rate',         [_val(r.get("win_rate"))      for r in results]),
        row('Trades closed',    [str(r['n_trades_closed'])    for r in results]),
        row('Avg trade return', [_val(r.get('avg_trade_return')) for r in results]),
        row('Max trade gain',   [_val(r.get('max_trade_gain'))   for r in results]),
        row('Max trade drop',   [_val(r.get('max_trade_drop'))   for r in results]),
        sep,
    ]

    txt_path = os.path.join(_HERE, f'comparison_{ts}.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'Summary txt saved  : {txt_path}')


# ── Grid search (uses local CSV for EQQQ, yfinance for rotation alts) ─────────

def run_grid_search_all(initial_capital: float = 10_000.0, maximize: str = 'cagr'):
    """
    Run grid search for every strategy.
    Note: individual grid_search functions still download via yfinance.
    EQQQ is available on Yahoo Finance as EQQQ.L (London listing).
    """
    from backtest_buy_the_dip     import grid_search as gs0
    from backtest_scalein_simple  import grid_search as gs1
    from backtest_scalein_hold    import grid_search as gs2
    from backtest_sma_crossover   import grid_search as gs3
    from backtest_macd_leverage   import grid_search as gs4
    from backtest_atr_sma         import grid_search as gs5
    from backtest_dual_momentum   import grid_search as gs6
    from backtest_vix_regime      import grid_search as gs7
    from backtest_vol_targeting   import grid_search as gs8
    from backtest_multi_asset     import grid_search as gs9

    yf_ticker = MAIN_TICKER  # local CSV takes priority in load_ohlcv

    def _run(label, fn, **kwargs):
        print(f'\n{"="*60}\nGRID SEARCH — {label}\n{"="*60}')
        return fn(**kwargs)

    df0 = _run('Buy the Dip',          gs0, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize)
    df1 = _run('Scale-in',             gs1, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize)
    df2 = _run('Scale-in + Hold',      gs2, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize)
    df3 = _run('SMA Crossover',        gs3, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize,
               alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET)
    df4 = _run('MACD',                 gs4, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize)
    df5 = _run('ATR-Adjusted SMA',     gs5, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize,
               alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET)
    df6 = _run('Dual Momentum',        gs6, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize,
               risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET_ROT)
    df7 = _run('VIX Regime',           gs7, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize)
    df8 = _run('Volatility Targeting', gs8, ticker=yf_ticker, period='max', initial_capital=initial_capital, maximize=maximize)
    df9 = _run('Multi-Asset Rotation', gs9,                   period='max', initial_capital=initial_capital, maximize=maximize,
               risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET_ROT)

    col_names = ['BuyDip', 'Scale-in', 'S-in+Hld', 'SMACross', 'MACD',
                 'ATR-SMA', 'DualMom', 'VIX', 'VolTgt', 'MultiAsset']
    dfs = [df0, df1, df2, df3, df4, df5, df6, df7, df8, df9]
    W   = 10
    sep = '=' * (27 + len(col_names) * (W + 1))

    print(f'\n{sep}')
    print(f'BEST RESULTS (by {maximize})')
    print(sep)
    print(f'{"":26}' + ''.join(f'{n:>{W}} ' for n in col_names))
    print('-' * len(sep))
    for key in ['cagr', 'total_return', 'max_drawdown', 'win_rate', 'n_trades']:
        vals = [str(df.iloc[0].get(key, 'N/A')) for df in dfs]
        print(f'{key:26}' + ''.join(f'{v:>{W}} ' for v in vals))
    print(sep)

    # ── Re-run full comparison with the best params from each grid search ─────
    def _pick(df, keys):
        """Extract parameter values from the top grid-search row.
        Floats that are whole numbers are cast to int (e.g. window params)."""
        row = df.iloc[0]
        result = {}
        for k in keys:
            if k not in row.index:
                continue
            v = row[k]
            if isinstance(v, float) and v == int(v):
                v = int(v)
            result[k] = v
        return result

    print(f'\n{"="*60}')
    print('RUNNING COMPARISON WITH BEST GRID SEARCH PARAMETERS')
    print(f'{"="*60}\n')

    run_comparison(
        initial_capital      = initial_capital,
        buy_dip_params       = _pick(df0, ['drop_pct']),
        scalein_params       = _pick(df1, ['bin_size_pct', 'max_drop_pct',
                                           'initial_alloc_pct', 'exit_sma_window']),
        scalein_hold_params  = _pick(df2, ['hold_pct', 'bin_size_pct', 'max_drop_pct',
                                           'initial_alloc_pct', 'exit_sma_window']),
        sma_crossover_params = _pick(df3, ['sma_window', 'band_pct']),
        macd_params          = _pick(df4, ['fast_ema', 'slow_ema', 'signal_ema']),
        atr_sma_params       = _pick(df5, ['sma_window', 'atr_window', 'atr_multiplier']),
        dual_momentum_params = _pick(df6, ['lookback']),
        vix_regime_params    = _pick(df7, ['vix_low', 'vix_high']),
        vol_targeting_params = _pick(df8, ['target_vol', 'vol_window', 'max_leverage']),
        multi_asset_params   = _pick(df9, ['lookback']),
    )

    return dfs


if __name__ == '__main__':
    run_grid_search_all()
