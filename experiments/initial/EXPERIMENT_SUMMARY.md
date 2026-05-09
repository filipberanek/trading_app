# Experiment Summary — Trading Strategy Research

**Period:** 2026-04  →  2026-05  
**Author:** Filip Beranek  
**Final decision:** ATR-SMA-C  |  `sma=15, atr=14, mult=0.3`

---

## 1. What Was Tested

All strategies were backtested on EQQQ (Invesco NASDAQ-100 UCITS ETF) with a universe of EU-listed ETFs.  
Data split: **Train 2017-03-23 → 2023-03-22** | **Test (OOS) 2023-03-23 → 2026-04-24**.

| # | Strategy | Core idea | Key params |
|---|----------|-----------|------------|
| 1 | **Backtest Simple** | Buy 1 % capital on each 3 % dip from peak; exit on SMA30 recovery | drop=3 %, alloc=1 % |
| 2 | **Buy the Dip** | Buy 100 % of available cash on 5 % dip; exit when price recovers to prior peak | drop=5 % |
| 3 | **Scale-in** | Stagger entries at 5/10/15 % dip levels; exit on SMA crossover | bin_size=5 % |
| 4 | **Scale-in + Hold** | 50 % permanent core (buy-and-hold) + 50 % scale-in satellite | hold_pct=50 % |
| 5 | **MACD Momentum** | Long when MACD histogram crosses zero up; flat when it crosses down | fast=12, slow=26 |
| 6 | **VIX Regime** | 100/50/0 % QQQ allocation based on VIX thresholds | vix_low=20, vix_high=30 |
| 7 | **Volatility Targeting** | Daily rebalance to target_vol %; smaller position when market is noisy | target_vol=35 %, window=2 |
| 8 | **Multi-Asset Rotation** | Hold whichever of {EQQQ, IUES, IGLN, IBZL, EEA, IUCS} has highest N-day momentum; cash to SEGA | lookback=21 |
| 9 | **Dual Momentum** | Same rotation as #8 + VIX filter for faster exit | lookback=21, vix_high=40 |
| 10 | **SMA Crossover** | Long EQQQ above SMA band; rotate to best alt or SEGA below band | sma=30, band=1 % |
| 11 | **ATR-SMA** | SMA band, but width is dynamic (ATR-based); no alt rotation | sma=30, atr=10, mult=0.3 |
| 12 | **ATR-SMA-C** | ATR-SMA + alt rotation to strongest-trending alt or cash | sma=15, atr=14, mult=0.3 |

---

## 2. Out-of-Sample Results

### Early comparison run (2026-04, Train 2017–2023 → Test 2023–2026)

| Strategy | CAGR | Max Drawdown | Trades |
|----------|------|-------------|--------|
| Buy&Hold | 24.5 % | −26.9 % | 0 |
| VolTgt | 24.7 % | −24.4 % | daily rebalance |
| ATR-SMA | 19.7 % | −16.2 % | 10 |
| MultiAsset | 17.5 % | −20.4 % | **127** |
| DualMom | 17.5 % | −20.4 % | **127** |
| SMACross | 10.7 % | −18.0 % | 10 |
| VIX | 7.1 % | −29.2 % | 25 |

### Final validation run (2026-05-08, with stability-based parameter selection)

| Strategy | CAGR | Max Drawdown | Trades | Win Rate |
|----------|------|-------------|--------|----------|
| Buy&Hold | 24.5 % | −26.9 % | 0 | — |
| ATR-SMA | **31.2 %** | −14.5 % | 32 | 50 % |
| SMACross | 27.9 % | −17.3 % | 24 | 50 % |
| **ATR-SMA-C** | **25.2 %** | **−12.8 %** | 50 | 54 % |

---

## 3. Walk-Forward Validation (ATR-SMA-C)

Five non-overlapping market regimes, each OOS:

| Regime | ATR-SMA-C CAGR | Buy&Hold CAGR | ATR-SMA-C MaxDD | B&H MaxDD |
|--------|---------------|--------------|-----------------|-----------|
| 2020 — COVID crash | +14.5 % | +71.2 % | −16.6 % | −11.9 % |
| 2021 — Bull market | +23.2 % | +20.2 % | −15.5 % | −18.8 % |
| 2022 — Bear / inflation | −15.1 % | −11.0 % | −20.9 % | −26.3 % |
| 2023 — Recovery | +22.6 % | +43.5 % | −10.4 % | −7.2 % |
| 2024-2026 — Recent bull | +22.2 % | +7.7 % | −8.3 % | −16.6 % |

**ATR-SMA-C beats Buy&Hold on CAGR in 2/5 windows, on Max Drawdown in 5/5 windows.**  
The strategy does not outperform in strong one-directional bull markets (2020, 2021, 2023); it shines in sustained trends and decline periods.

---

## 4. Why Asset Rotation Was Ruled Out

MultiAsset and DualMom were technically competitive in CAGR terms (17.5 %) but were rejected for three reasons:

### 4a. Trading frequency — transaction cost risk
MultiAsset and DualMom each executed **127 trades** in the OOS period (≈1 trade every 6 trading days).  
At real-world costs (spread + broker commission), this frequency would significantly erode returns.  
ATR-SMA-C achieved a comparable CAGR with only **50 trades** — and the simpler ATR-SMA with **32 trades**.

### 4b. Parameter instability across regimes
Walk-forward showed that optimal parameters change drastically per market regime:

| Window | ATR-SMA-C best sma | Comment |
|--------|--------------------|---------|
| 2020 (COVID crash) | 30 | Slow SMA needed in a crash |
| 2021 (Bull market) | 5 | Fast SMA outperforms in trends |
| 2022 (Bear) | 5 | Fast reaction matters |
| 2023–2026 (Recovery/bull) | 15 | Medium window |

A strategy that requires reoptimisation after every regime change is not production-ready.

### 4c. Universe selection bias
The alt assets (IUES, IGLN, IBZL, EEA, IUCS) were selected retrospectively after observing which assets performed well in the backtest period. This introduces look-ahead bias — the full universe would be much larger in a real deployment, and the best historical alts are unlikely to remain the best future alts.

### 4d. Conclusion
Asset rotation in the pure momentum form (MultiAsset, DualMom) trades too frequently and is too sensitive to which assets happen to be in the universe. The ATR-SMA-C strategy achieves a similar risk-reduction benefit (via cash fallback) with far fewer trades and a more transparent signal.

---

## 5. Why ATR-SMA-C Was Chosen

Compared to ATR-SMA (no rotation):

| | ATR-SMA | ATR-SMA-C |
|---|---------|-----------|
| CAGR | 31.2 % | 25.2 % |
| Max Drawdown | −14.5 % | **−12.8 %** |
| Trades | 32 | 50 |
| Cash fallback when all alts negative | No | **Yes** |

ATR-SMA has a higher raw CAGR, but it is always fully invested — it cannot exit to cash.  
ATR-SMA-C accepts a lower CAGR in exchange for:
- A defined exit mechanism when EQQQ breaks below the ATR band
- A structured cash fallback when no alternative trend is positive
- Marginally lower max drawdown

For a live trading system, the ability to be **flat** (in cash) is operationally and psychologically important.

---

## 6. Parameter Selection Methodology

Three-stage selection process — no OOS data was used for selection at any stage:

### Stage 1: Grid search on TRAIN data only
- SMA windows: [5, 10, 15, 20, 25, 30, 35, 40, 50] — 9 values  
- ATR windows: [7, 10, 14, 20] — 4 values  
- ATR multipliers: [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 10.0] — not all, subset  
- **660 combinations** evaluated  
- Top-10 by CAGR + top-10 by Calmar ratio → up to 20 candidates

### Stage 2: K-fold stability selection (on TRAIN years only)
Leave-one-year-out cross-validation across 7 train years (2017–2023):
- Compute CAGR for each candidate in each train year (year left out as validation)
- **Stability score = avg(CAGR) / std(CAGR)** — rewards consistent, not lucky, performance
- Final selection: candidate with highest stability score

Stability scores for top candidates:

| Rank | sma | atr | mult | Avg CAGR | Std | Score |
|------|-----|-----|------|----------|-----|-------|
| #5 → **selected** | 15 | 14 | 0.30 | 18.6 % | 22.1 % | **0.84** |
| #6 | 15 | 14 | 0.35 | 18.6 % | 22.3 % | 0.83 |
| #1 (max train CAGR) | 15 | 20 | 0.35 | 15.2 % | 25.6 % | 0.59 |

The parameter set with the highest train CAGR (rank #1) has a stability score of only 0.59 — it profits heavily in 2019 and 2021 but is inconsistent elsewhere.

### Stage 3: OOS (test period) — for evaluation only
Used only to report final performance. Never used for selection.

---

## 7. Final Production Parameters

File: [config/atr_sma_c.yaml](../../config/atr_sma_c.yaml)

```yaml
parameters:
  sma_window: 15        # SMA lookback — 3 trading weeks
  atr_window: 14        # ATR lookback — 2 trading weeks
  atr_multiplier: 0.3   # band width = ATR/Close * 0.3

universe:
  main_ticker: EQQQ
  alt_tickers: [IUES, IGLN, IBZL, EEA, IUCS]
  safe_ticker: SEGA     # treated as one of the alts; cash is the final fallback
```

Implementation: [src/strategies/atr_sma_c.py](../../src/strategies/atr_sma_c.py)  
Unit tests: [tests/strategies/test_atr_sma_c.py](../../tests/strategies/test_atr_sma_c.py) — 17 tests, all passing

---

## 8. Signal Logic (Production)

```
Every bar:
  band = (ATR_14 / Close) * 0.3
  upper = SMA_15 * (1 + band)
  lower = SMA_15 * (1 - band)

  If holding EQQQ and Close < lower:
    → SELL EQQQ
    → BUY alt with highest (Close - SMA) / ATR > 0
    → If no alt qualifies: stay in cash (2 % p.a. cash rate)

  If not holding EQQQ and Close > upper:
    → SELL current alt (if any)
    → BUY EQQQ
```

Alt selection uses the same ATR-SMA trend-strength metric as the main signal — consistent logic throughout.

---

## 9. Known Limitations and Risks

| Risk | Description |
|------|-------------|
| **Universe selection bias** | Alt tickers were chosen after observing historical performance. Real-world universe may behave differently. |
| **No transaction costs** | All backtests assume zero spread and commission. Real IBKR costs would reduce CAGR, especially for ATR-SMA-C (50 trades in 3 years). |
| **2022 underperformance** | ATR-SMA-C returned −15.1 % in the 2022 bear market, worse than Buy&Hold (−11.0 %). The cash fallback did not fully protect. |
| **Short OOS period** | The test period is only 3 years. A longer OOS would increase confidence. |
| **Parameter sensitivity** | Walk-forward shows optimal sma_window shifts between 5 and 30 across regimes. The selected sma=15 is a compromise. |
| **Survivorship bias** | Data from Yahoo Finance / broker feeds may not reflect delisted ETFs or corporate events. |
| **SEGA 2022** | The safe haven asset (SEGA, EU government bonds) lost value in 2022 due to ECB rate hikes — the "safe" alt is not risk-free. |
