"""
Strategy Comparison — Walk-Forward (Train / Test Split)

Identical to compare_strategies.py with one key difference:
  Train : first TRAIN_YEARS years  → grid search finds optimal params (in-sample)
  Test  : remaining data           → out-of-sample evaluation with those params

Outputs: comparison_ml_YYYYMMDD_HHMM.{png,txt}  (saved next to this file)
"""

import os
import sys
import itertools
from datetime import datetime
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE    = os.path.dirname(__file__)
ROOT     = os.path.dirname(_HERE)
_APP     = os.path.dirname(os.path.dirname(ROOT))
DATA_DIR = os.path.join(_APP, 'data_preprocessing', 'input_data')

# ── Ticker config (mirrors compare_strategies.py) ─────────────────────────────

MAIN_TICKER    = 'EQQQ'
ALT_ASSETS     = ('IUES', 'IGLN', 'IDTL', 'IBZL', 'EEA', 'IUCS')
SAFE_ASSET     = 'XEON'   # safe haven for all rotation strategies
SAFE_ASSET_ROT = SAFE_ASSET
RISKY_ASSETS   = ('EQQQ', 'IUES', 'IGLN', 'IBZL', 'EEA', 'IUCS')
ALL_ROTATION   = list(RISKY_ASSETS) + [SAFE_ASSET]

TRAIN_YEARS = 6   # first N years used for grid search

# ── Strategy imports ──────────────────────────────────────────────────────────

for _folder in ('trading_algo_backtest_scalein', 'trading_algo_backtest_scalein_hold',
                'trading_algo_sma_crossover', 'trading_algo_macd_leverage',
                'trading_algo_buy_the_dip', 'trading_algo_atr_sma',
                'trading_algo_dual_momentum', 'trading_algo_vix_regime',
                'trading_algo_vol_targeting', 'trading_algo_multi_asset',
                'trading_algo_atr_sma_cash'):
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
from backtest_atr_sma_cash    import run_backtest_atr_sma_cash


# ── Data loading ──────────────────────────────────────────────────────────────

def load_local(ticker: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f'{ticker}.csv')
    if not os.path.exists(path):
        raise FileNotFoundError(f'Local CSV not found: {path}')
    df = pd.read_csv(path, parse_dates=['Date'], index_col='Date')
    df.index = pd.to_datetime(df.index)
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()


def load_all_local(tickers: list) -> dict:
    result = {}
    for t in tickers:
        try:
            result[t] = load_local(t)
        except FileNotFoundError as e:
            print(f'  WARNING: {e}')
    return result


# ── Small helpers ─────────────────────────────────────────────────────────────

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


def _pick(df, keys):
    """Top row of grid-search results → param dict.  Float whole-numbers → int."""
    if df.empty:
        return {}
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


def _align_vix(vix_df: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    return vix_df.reindex(df.index, method='ffill').dropna()


# ── Inline grid searches (operate on pre-sliced dataframes) ──────────────────
# Each function returns a DataFrame sorted by `maximize`, best row first.

def _gs_buy_dip(df, capital, maximize):
    results = []
    for drop in (0.02, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20):
        try:
            r = run_backtest_buy_the_dip(
                initial_capital=capital, drop_pct=drop, verbose=False, df=df)
            results.append({'drop_pct': drop, 'cagr': r['cagr'],
                            'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'],
                            'n_trades': r['n_trades_closed']})
        except Exception as e:
            print(f'      ERR drop={drop}: {e}')
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_scalein(df, capital, maximize):
    combos = [
        (b, d, a, s)
        for b, d, a, s in itertools.product(
            (0.05, 0.07, 0.10, 0.12, 0.15),
            (0.10, 0.15, 0.20, 0.30),
            (0.10, 0.20, 0.30, 0.40, 0.50),
            (30, 50, 60, 75))
        if b < d
    ]
    results = []
    for b, d, a, s in combos:
        try:
            r = run_backtest_scalein(
                initial_capital=capital, bin_size_pct=b, max_drop_pct=d,
                initial_alloc_pct=a, exit_sma_window=s, verbose=False, df=df)
            results.append({'bin_size_pct': b, 'max_drop_pct': d,
                            'initial_alloc_pct': a, 'exit_sma_window': s,
                            'cagr': r['cagr'], 'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_scalein_hold(df, capital, maximize):
    combos = [
        (h, b, d, a, s)
        for h, b, d, a, s in itertools.product(
            (0.01, 0.05, 0.10),
            (0.05, 0.07, 0.10, 0.12, 0.15),
            (0.10, 0.15, 0.20, 0.30),
            (0.05, 0.10, 0.20, 0.30),
            (30, 50, 60, 75))
        if b < d
    ]
    results = []
    for h, b, d, a, s in combos:
        try:
            r = run_backtest_scalein_hold(
                initial_capital=capital, hold_pct=h, bin_size_pct=b, max_drop_pct=d,
                initial_alloc_pct=a, exit_sma_window=s, verbose=False, df=df)
            results.append({'hold_pct': h, 'bin_size_pct': b, 'max_drop_pct': d,
                            'initial_alloc_pct': a, 'exit_sma_window': s,
                            'cagr': r['cagr'], 'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_sma_crossover(df, alt_dfs, capital, maximize):
    combos = list(itertools.product(
        (50, 100, 150, 200, 225, 250, 300, 350, 400),
        (0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.075, 0.10),
    ))
    results = []
    for sma_w, band in combos:
        try:
            r = run_backtest_sma_crossover(
                ticker=MAIN_TICKER, initial_capital=capital, sma_window=sma_w, band_pct=band,
                alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET,
                verbose=False, df=df, alt_dfs=alt_dfs)
            results.append({'sma_window': sma_w, 'band_pct': band, 'cagr': r['cagr'],
                            'total_return': r['total_return'], 'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_macd(df, capital, maximize):
    combos = [(f, s, sig)
              for f, s, sig in itertools.product(
                  (4, 8, 10, 12, 15), (20, 24, 26, 30, 45), (4, 7, 9, 12))
              if f < s]
    results = []
    for f, s, sig in combos:
        try:
            r = run_backtest_macd_leverage(
                ticker=MAIN_TICKER, initial_capital=capital,
                fast_ema=f, slow_ema=s, signal_ema=sig, verbose=False, df=df)
            results.append({'fast_ema': f, 'slow_ema': s, 'signal_ema': sig,
                            'cagr': r['cagr'], 'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_atr_sma(df, alt_dfs, capital, maximize):
    combos = list(itertools.product(
        (100, 150, 200, 250),
        (10, 14, 20),
        (0.5, 1.0, 1.5, 2.0),
    ))
    results = []
    for sma_w, atr_w, atr_m in combos:
        try:
            r = run_backtest_atr_sma(
                ticker=MAIN_TICKER, initial_capital=capital,
                sma_window=sma_w, atr_window=atr_w, atr_multiplier=atr_m,
                alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET,
                verbose=False, df=df, alt_dfs=alt_dfs)
            results.append({'sma_window': sma_w, 'atr_window': atr_w, 'atr_multiplier': atr_m,
                            'cagr': r['cagr'], 'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_atr_sma_cash(df, alt_dfs, capital, maximize):
    combos = list(itertools.product(
        (100, 150, 200, 250),
        (10, 14, 20),
        (0.5, 1.0, 1.5, 2.0),
    ))
    results = []
    for sma_w, atr_w, atr_m in combos:
        try:
            r = run_backtest_atr_sma_cash(
                ticker=MAIN_TICKER, initial_capital=capital,
                sma_window=sma_w, atr_window=atr_w, atr_multiplier=atr_m,
                alt_assets=ALT_ASSETS + (SAFE_ASSET,),
                verbose=False, df=df, alt_dfs=alt_dfs)
            results.append({'sma_window': sma_w, 'atr_window': atr_w, 'atr_multiplier': atr_m,
                            'cagr': r['cagr'], 'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_dual_momentum(dfs, capital, maximize):
    results = []
    for lb in (21, 42, 63, 126, 189, 252):
        try:
            r = run_backtest_dual_momentum(
                initial_capital=capital, lookback=lb,
                risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET_ROT,
                verbose=False, dfs=dfs)
            results.append({'lookback': lb, 'cagr': r['cagr'],
                            'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception as e:
            print(f'      ERR lb={lb}: {e}')
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_vix_regime(df, vix_df, capital, maximize):
    vix_aligned = _align_vix(vix_df, df)
    combos = [(l, h) for l in (15, 18, 20, 22, 25) for h in (25, 28, 30, 35, 40) if l < h]
    results = []
    for vl, vh in combos:
        try:
            r = run_backtest_vix_regime(
                initial_capital=capital, vix_low=vl, vix_high=vh,
                verbose=False, df=df, vix_df=vix_aligned)
            results.append({'vix_low': vl, 'vix_high': vh, 'cagr': r['cagr'],
                            'total_return': r['total_return'], 'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_vol_targeting(df, capital, maximize):
    combos = list(itertools.product(
        (0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30, 0.35, 0.40),
        (2, 3, 5, 7, 10, 20, 30, 40, 60),
        (1.0,),
    ))
    results = []
    for tv, vw, ml in combos:
        try:
            r = run_backtest_vol_targeting(
                initial_capital=capital, target_vol=tv, vol_window=vw,
                max_leverage=ml, verbose=False, df=df)
            results.append({'target_vol': tv, 'vol_window': vw, 'max_leverage': ml,
                            'cagr': r['cagr'], 'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': None, 'n_trades': 0})
        except Exception:
            pass
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


def _gs_multi_asset(dfs, capital, maximize):
    results = []
    for lb in (21, 42, 63, 126, 189, 252):
        try:
            r = run_backtest_multi_asset(
                initial_capital=capital, lookback=lb,
                risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET_ROT,
                verbose=False, dfs=dfs)
            results.append({'lookback': lb, 'cagr': r['cagr'],
                            'total_return': r['total_return'],
                            'max_drawdown': r['max_drawdown'],
                            'win_rate': r['win_rate'], 'n_trades': r['n_trades_closed']})
        except Exception as e:
            print(f'      ERR lb={lb}: {e}')
    return pd.DataFrame(results).sort_values(maximize, ascending=False).reset_index(drop=True)


# ── Main walk-forward comparison ─────────────────────────────────────────────

def run_comparison_ml(train_years: int = TRAIN_YEARS,
                      initial_capital: float = 10_000.0,
                      maximize: str = 'cagr'):
    """
    1. Load full local CSV data.
    2. Split at `train_years` from first date.
    3. Grid search every strategy on TRAIN slice.
    4. Evaluate every strategy on TEST slice with best params.
    5. Print table + save chart + save txt.
    """

    # ── Load ──────────────────────────────────────────────────────────────────
    print(f'Loading {MAIN_TICKER} from local CSV...')
    raw_df = load_local(MAIN_TICKER)
    print(f'Loading rotation tickers: {ALL_ROTATION}')
    raw_multi = load_all_local(ALL_ROTATION)
    print('Downloading VIX from yfinance...')
    raw_vix = fetch_vix('max')
    raw_vix.index = pd.to_datetime(raw_vix.index)

    # ── Split ─────────────────────────────────────────────────────────────────
    cutoff = raw_df.index[0] + pd.DateOffset(years=train_years)

    train_df = raw_df[raw_df.index < cutoff].copy()
    test_df  = raw_df[raw_df.index >= cutoff].copy()

    train_multi = {t: df[df.index < cutoff].copy() for t, df in raw_multi.items()}
    test_multi  = {t: df[df.index >= cutoff].copy() for t, df in raw_multi.items()}

    train_vix = raw_vix[raw_vix.index < cutoff].copy()
    test_vix  = raw_vix[raw_vix.index >= cutoff].copy()

    sep = '─' * 60
    print(f'\n{sep}')
    print(f'TRAIN  {train_df.index[0].date()} → {train_df.index[-1].date()}'
          f'  ({len(train_df)} days, ~{train_years} years)')
    print(f'TEST   {test_df.index[0].date()} → {test_df.index[-1].date()}'
          f'  ({len(test_df)} days, ~{round(len(test_df)/252, 1)} years)')
    print(f'{sep}\n')

    names = ['Buy&Hold', 'BuyDip', 'Scale-in', 'S-in+Hld', 'SMACross', 'MACD',
             'ATR-SMA', 'ATR-SMA-C', 'DualMom', 'VIX', 'VolTgt', 'MultiAsset']

    # ── Grid search on TRAIN ──────────────────────────────────────────────────
    print('=== TRAIN — Grid search ===\n')

    print('  Buy the Dip...')
    gs0 = _gs_buy_dip(train_df, initial_capital, maximize)

    print('  Scale-in...')
    gs1 = _gs_scalein(train_df, initial_capital, maximize)

    print('  Scale-in + Hold...')
    gs2 = _gs_scalein_hold(train_df, initial_capital, maximize)

    print('  SMA Crossover...')
    gs3 = _gs_sma_crossover(train_df, train_multi, initial_capital, maximize)

    print('  MACD...')
    gs4 = _gs_macd(train_df, initial_capital, maximize)

    print('  ATR-Adjusted SMA...')
    gs5 = _gs_atr_sma(train_df, train_multi, initial_capital, maximize)

    print('  ATR-SMA Cash...')
    gs5c = _gs_atr_sma_cash(train_df, train_multi, initial_capital, maximize)

    print('  Dual Momentum...')
    gs6 = _gs_dual_momentum(train_multi, initial_capital, maximize)

    print('  VIX Regime...')
    gs7 = _gs_vix_regime(train_df, train_vix, initial_capital, maximize)

    print('  Volatility Targeting...')
    gs8 = _gs_vol_targeting(train_df, initial_capital, maximize)

    print('  Multi-Asset Rotation...')
    gs9 = _gs_multi_asset(train_multi, initial_capital, maximize)

    # ── Best params ───────────────────────────────────────────────────────────
    p0 = _pick(gs0, ['drop_pct'])
    p1 = _pick(gs1, ['bin_size_pct', 'max_drop_pct', 'initial_alloc_pct', 'exit_sma_window'])
    p2 = _pick(gs2, ['hold_pct', 'bin_size_pct', 'max_drop_pct', 'initial_alloc_pct', 'exit_sma_window'])
    p3 = _pick(gs3, ['sma_window', 'band_pct'])
    p4 = _pick(gs4, ['fast_ema', 'slow_ema', 'signal_ema'])
    p5  = _pick(gs5,  ['sma_window', 'atr_window', 'atr_multiplier'])
    p5c = _pick(gs5c, ['sma_window', 'atr_window', 'atr_multiplier'])
    p6 = _pick(gs6, ['lookback'])
    p7 = _pick(gs7, ['vix_low', 'vix_high'])
    p8 = _pick(gs8, ['target_vol', 'vol_window', 'max_leverage'])
    p9 = _pick(gs9, ['lookback'])

    best_params = [p0, p1, p2, p3, p4, p5, p5c, p6, p7, p8, p9]

    print(f'\nBest train params (optimised on {train_df.index[0].date()} – {train_df.index[-1].date()}):')
    for name, p in zip(names, best_params):
        print(f'  {name:12}  {p}')

    # ── Evaluate on TEST ──────────────────────────────────────────────────────
    print(f'\n=== TEST — Out-of-sample evaluation ({test_df.index[0].date()} – {test_df.index[-1].date()}) ===\n')

    test_vix_aligned = _align_vix(test_vix, test_df)

    print('  Buy the Dip...')
    r0 = run_backtest_buy_the_dip(
        initial_capital=initial_capital, verbose=False, df=test_df, **p0)

    print('  Scale-in...')
    r1 = run_backtest_scalein(
        initial_capital=initial_capital, verbose=False, df=test_df, **p1)

    print('  Scale-in + Hold...')
    r2 = run_backtest_scalein_hold(
        initial_capital=initial_capital, verbose=False, df=test_df, **p2)

    print('  SMA Crossover...')
    r3 = run_backtest_sma_crossover(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=test_df, alt_dfs=test_multi,
        alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET, **p3)

    print('  MACD...')
    r4 = run_backtest_macd_leverage(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=test_df, **p4)

    print('  ATR-Adjusted SMA...')
    r5 = run_backtest_atr_sma(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=test_df, alt_dfs=test_multi,
        alt_assets=ALT_ASSETS, safe_asset=SAFE_ASSET, **p5)

    print('  ATR-SMA Cash...')
    r5c = run_backtest_atr_sma_cash(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        df=test_df, alt_dfs=test_multi,
        alt_assets=ALT_ASSETS + (SAFE_ASSET,), **p5c)

    print('  Dual Momentum...')
    r6 = run_backtest_dual_momentum(
        ticker=MAIN_TICKER, initial_capital=initial_capital, verbose=False,
        dfs=test_multi, risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET_ROT, **p6)

    print('  VIX Regime...')
    r7 = run_backtest_vix_regime(
        initial_capital=initial_capital, verbose=False,
        df=test_df, vix_df=test_vix_aligned, **p7)

    print('  Volatility Targeting...')
    r8 = run_backtest_vol_targeting(
        initial_capital=initial_capital, verbose=False, df=test_df, **p8)

    print('  Multi-Asset Rotation...')
    r9 = run_backtest_multi_asset(
        initial_capital=initial_capital, verbose=False,
        dfs=test_multi, risky_assets=RISKY_ASSETS, safe_asset=SAFE_ASSET_ROT, **p9)

    r_bh    = _buy_and_hold_result(test_df, initial_capital)
    results = [r_bh, r0, r1, r2, r3, r4, r5, r5c, r6, r7, r8, r9]

    # ── Print table ───────────────────────────────────────────────────────────
    W   = 10
    sep2 = '=' * (27 + len(names) * (W + 1))

    print(f'\n{sep2}')
    print(f'OUT-OF-SAMPLE RESULTS  ({test_df.index[0].date()} – {test_df.index[-1].date()})')
    print(f'{"":26}' + ''.join(f'{n:>{W}} ' for n in names))
    print(sep2)

    def row(label, vals):
        return f'{label:26}' + ''.join(f'{str(v):>{W}} ' for v in vals)

    print(row('Final equity',     [f'{r["final_equity"]:,.0f}'  for r in results]))
    print(row('Total return',     [f'{r["total_return"]:.1%}'   for r in results]))
    print(row('CAGR',             [f'{r["cagr"]:.2%}'           for r in results]))
    print(row('Max drawdown',     [f'{r["max_drawdown"]:.2%}'   for r in results]))
    print(row('Win rate',         [_val(r.get('win_rate'))       for r in results]))
    print(row('Trades closed',    [str(r['n_trades_closed'])     for r in results]))
    print(row('Avg trade return', [_val(r.get('avg_trade_return')) for r in results]))
    print(row('Max trade gain',   [_val(r.get('max_trade_gain')) for r in results]))
    print(row('Max trade drop',   [_val(r.get('max_trade_drop')) for r in results]))
    print(sep2)

    ts = datetime.now().strftime('%Y%m%d_%H%M')
    _plot_comparison_ml(test_df, results, names, ts, train_df)
    _save_summary_txt_ml(results, names, best_params, ts, train_df, test_df)
    return results


# ── Plot ──────────────────────────────────────────────────────────────────────

def _plot_comparison_ml(test_df, results, names, ts, train_df):
    colors = ['gray', 'tab:purple', 'tab:blue', 'tab:orange', 'tab:green',
              'tab:red', 'tab:cyan', 'goldenrod', 'tab:pink', 'tab:brown', 'tab:olive', 'tab:gray']

    all_labels = names
    all_cagrs  = [r['cagr'] for r in results]
    all_dds    = [r['max_drawdown'] for r in results]
    all_trades = [r['n_trades_closed'] for r in results]

    x = list(range(len(all_labels)))
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(24, 7))

    date_fmt = f'{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:]}'
    train_range = f'{train_df.index[0].date()} – {train_df.index[-1].date()}'
    test_range  = f'{test_df.index[0].date()} – {test_df.index[-1].date()}'
    fig.suptitle(
        f'Strategy Comparison (OUT-OF-SAMPLE) — {MAIN_TICKER}  |  {date_fmt}\n'
        f'Train: {train_range}   ·   Test: {test_range}',
        fontsize=11, fontweight='bold')

    def _annotate(ax, bars, vals, fmt, va='bottom', offset=0.1):
        for bar, val in zip(bars, vals):
            if val is None:
                continue
            y = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2,
                    y + offset if va == 'bottom' else y - offset,
                    fmt(val), ha='center', va=va, fontsize=8, fontweight='bold')

    bars1 = ax1.bar(x, [v * 100 if v is not None else 0 for v in all_cagrs],
                    color=colors, edgecolor='white', linewidth=0.5)
    ax1.set_title(f'CAGR — test period')
    ax1.set_ylabel('CAGR (%)')
    ax1.set_xticks(x); ax1.set_xticklabels(all_labels, rotation=30, ha='right', fontsize=9)
    ax1.grid(axis='y', alpha=0.4)
    _annotate(ax1, bars1, all_cagrs, lambda v: f'{v:.1%}')

    bars2 = ax2.bar(x, [v * 100 for v in all_dds],
                    color=colors, edgecolor='white', linewidth=0.5)
    ax2.set_title(f'Max Drawdown — test period')
    ax2.set_ylabel('Max Drawdown (%)')
    ax2.set_xticks(x); ax2.set_xticklabels(all_labels, rotation=30, ha='right', fontsize=9)
    ax2.grid(axis='y', alpha=0.4)
    _annotate(ax2, bars2, all_dds, lambda v: f'{v:.1%}', va='top', offset=0.3)

    bars3 = ax3.bar(x, all_trades, color=colors, edgecolor='white', linewidth=0.5)
    ax3.set_title(f'Closed Trades — test period')
    ax3.set_ylabel('Number of trades')
    ax3.set_xticks(x); ax3.set_xticklabels(all_labels, rotation=30, ha='right', fontsize=9)
    ax3.grid(axis='y', alpha=0.4)
    _annotate(ax3, bars3, all_trades, lambda v: str(int(v)))

    fig.tight_layout()
    fig_path = os.path.join(_HERE, f'comparison_ml_{ts}.png')
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)
    print(f'\nComparison plot saved: {fig_path}')


# ── Text summary ──────────────────────────────────────────────────────────────

def _save_summary_txt_ml(results, names, best_params, ts, train_df, test_df):
    W   = 12
    sep = '=' * (28 + len(names) * (W + 1))
    date_fmt = f'{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:]}'

    def row(label, vals):
        return f'{label:27}' + ''.join(f'{str(v):>{W}} ' for v in vals)

    param_lines = []
    for name, p in zip(names, best_params):
        param_lines.append(f'  {name:12}  {p}')

    lines = [
        f'Strategy comparison (walk-forward) — {MAIN_TICKER}',
        f'Generated  : {date_fmt}',
        f'Train      : {train_df.index[0].date()} – {train_df.index[-1].date()}'
        f'  ({len(train_df)} trading days)',
        f'Test       : {test_df.index[0].date()} – {test_df.index[-1].date()}'
        f'  ({len(test_df)} trading days)',
        f'Rotation   : {", ".join(list(RISKY_ASSETS))} + CASH (DualMom/MultiAsset) / {SAFE_ASSET} (SMACross/ATR-SMA)',
        '',
        '--- Best parameters found on TRAIN data ---',
        *param_lines,
        '',
        '--- Out-of-sample results (TEST data) ---',
        sep,
        f'{"":27}' + ''.join(f'{n:>{W}} ' for n in names),
        sep,
        row('CAGR',             [f'{r["cagr"]:.2%}'          for r in results]),
        row('Total return',     [f'{r["total_return"]:.1%}'  for r in results]),
        row('Final equity',     [f'{r["final_equity"]:,.0f}' for r in results]),
        row('Max drawdown',     [f'{r["max_drawdown"]:.2%}'  for r in results]),
        row('Win rate',         [_val(r.get('win_rate'))      for r in results]),
        row('Trades closed',    [str(r['n_trades_closed'])    for r in results]),
        row('Avg trade return', [_val(r.get('avg_trade_return')) for r in results]),
        row('Max trade gain',   [_val(r.get('max_trade_gain'))   for r in results]),
        row('Max trade drop',   [_val(r.get('max_trade_drop'))   for r in results]),
        sep,
    ]

    txt_path = os.path.join(_HERE, f'comparison_ml_{ts}.txt')
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'Summary txt saved  : {txt_path}')


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    run_comparison_ml()
