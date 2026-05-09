"""
Safe Haven Comparison — DualMom & MultiAsset

Tests IGLN (Gold), IUES (Energy), IUCS (Consumer Staples) as safe haven assets.

Key design: each candidate stays IN the risky rotation pool AND acts as safe haven.
  - When candidate has best positive momentum  -> selected as rotation winner
  - When ALL risky assets have negative momentum -> selected as defensive fallback

No bonds in rotation or as safe haven (SEGA and IDTL excluded entirely).

Grid search lookback on TRAIN, evaluate on TEST.
"""

import os
import sys
import pandas as pd

_HERE    = os.path.dirname(os.path.abspath(__file__))
ROOT     = os.path.dirname(_HERE)
_APP     = os.path.dirname(os.path.dirname(ROOT))
DATA_DIR = os.path.join(_APP, 'data_preprocessing', 'input_data')

sys.path.insert(0, os.path.join(ROOT, 'trading_algo_multi_asset'))
from backtest_multi_asset import run_backtest_multi_asset

TRAIN_YEARS = 6
INITIAL_CAP = 10_000.0
LOOKBACKS   = (21, 42, 63, 126, 189, 252)

# Rotation universe — no bonds (SEGA, IDTL excluded entirely)
RISKY_ASSETS = ('EQQQ', 'IUES', 'IGLN', 'IBZL', 'EEA', 'IUCS')

# Each candidate is BOTH a rotation asset AND the safe haven fallback
# (stays in RISKY_ASSETS, also used as safe_asset)
CANDIDATES = {
    'IGLT (UK Gilts)':             'IGLT',
    'IGLO (Global Govt Bond)':     'IGLO',
    'XEON (EUR Overnight)':        'XEON',
    'IGLN (Physical Gold)':        'IGLN',
    'IUCS (Consumer Staples)':     'IUCS',
    'SEGA (Euro Agg Bond)':        'SEGA',
}


def load_local(ticker: str) -> pd.DataFrame:
    path = os.path.join(DATA_DIR, f'{ticker}.csv')
    if not os.path.exists(path):
        raise FileNotFoundError(f'Missing CSV: {path}')
    df = pd.read_csv(path, parse_dates=['Date'], index_col='Date')
    df.index = pd.to_datetime(df.index)
    return df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()


def main():
    print('Loading data...')
    raw = {}
    all_tickers = set(RISKY_ASSETS) | set(CANDIDATES.values())
    for t in all_tickers:
        try:
            raw[t] = load_local(t)
        except FileNotFoundError as e:
            print(f'  WARNING: {e}')

    first_date = raw['EQQQ'].index[0]
    cutoff     = first_date + pd.DateOffset(years=TRAIN_YEARS)

    train_dfs = {t: df[df.index <  cutoff].copy() for t, df in raw.items()}
    test_dfs  = {t: df[df.index >= cutoff].copy() for t, df in raw.items()}

    train_end = max(df.index[-1] for df in train_dfs.values()).date()
    test_end  = max(df.index[-1] for df in test_dfs.values()).date()
    print(f'Train: {first_date.date()} - {train_end}  ({len(list(train_dfs.values())[0])} days)')
    print(f'Test : {cutoff.date()} - {test_end}  ({len(list(test_dfs.values())[0])} days)')
    print(f'Rotation pool: {RISKY_ASSETS}\n')

    rows = []

    for label, safe in CANDIDATES.items():
        print(f'Testing safe haven: {label}')
        print(f'  -> asset stays in rotation AND acts as defensive fallback')

        # Grid search on TRAIN
        best_lb, best_train_cagr = None, -999.0
        for lb in LOOKBACKS:
            try:
                r = run_backtest_multi_asset(
                    initial_capital=INITIAL_CAP, lookback=lb,
                    risky_assets=RISKY_ASSETS,
                    safe_asset=safe,
                    verbose=False, dfs=train_dfs,
                )
                if r['cagr'] is not None and r['cagr'] > best_train_cagr:
                    best_train_cagr = r['cagr']
                    best_lb = lb
            except Exception as e:
                print(f'    WARN lb={lb}: {e}')

        print(f'  Best lookback (train): {best_lb} days  |  train CAGR: {best_train_cagr:.1%}')

        # Evaluate on TEST
        try:
            rt = run_backtest_multi_asset(
                initial_capital=INITIAL_CAP, lookback=best_lb,
                risky_assets=RISKY_ASSETS,
                safe_asset=safe,
                verbose=False, dfs=test_dfs,
            )
            rows.append({
                'Safe haven':   label,
                'Lookback':     best_lb,
                'CAGR':         rt['cagr'],
                'Max DD':       rt['max_drawdown'],
                'Total return': rt['total_return'],
                'Final equity': rt['final_equity'],
                'Win rate':     rt['win_rate'],
                'Trades':       rt['n_trades_closed'],
            })
            print(f'  TEST  ->  CAGR: {rt["cagr"]:.2%}  |  Max DD: {rt["max_drawdown"]:.2%}'
                  f'  |  Final equity: {rt["final_equity"]:,.0f}\n')
        except Exception as e:
            print(f'  ERROR on test: {e}\n')

    # Summary table
    df = pd.DataFrame(rows)
    df_fmt = df.copy()
    df_fmt['CAGR']         = df['CAGR'].map(lambda v: f'{v:.2%}' if v is not None else 'N/A')
    df_fmt['Max DD']       = df['Max DD'].map(lambda v: f'{v:.2%}' if v is not None else 'N/A')
    df_fmt['Total return'] = df['Total return'].map(lambda v: f'{v:.1%}' if v is not None else 'N/A')
    df_fmt['Final equity'] = df['Final equity'].map(lambda v: f'{v:,.0f}' if v is not None else 'N/A')
    df_fmt['Win rate']     = df['Win rate'].map(lambda v: f'{v:.1%}' if v is not None else 'N/A')

    sep = '=' * 90
    print(f'\n{sep}')
    print('SAFE HAVEN COMPARISON — MultiAsset rotation (out-of-sample TEST)')
    print(f'Rotation pool (all 6 stay active): {RISKY_ASSETS}')
    print(sep)
    print(df_fmt.to_string(index=False))
    print(sep)

    out_csv = os.path.join(_HERE, 'safe_haven_comparison.csv')
    df.to_csv(out_csv, index=False)
    print(f'\nSaved: {out_csv}')


if __name__ == '__main__':
    main()
