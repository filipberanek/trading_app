# Trading Strategies — Backtest Experiments

Tato složka obsahuje 11 backtestovaných obchodních strategií na akciovém ETF **QQQ** (Nasdaq-100).
Každá strategie testuje jiný přístup k tomu, kdy koupit, kdy prodat a jak veliký být v trhu.

---

## Obsah

1. [Jak funguje backtesting](#jak-funguje-backtesting)
2. [Společné předpoklady](#společné-předpoklady)
3. [Strategie](#strategie)
   - [1. Backtest Simple — Nákup poklesu od vrcholu](#1-backtest-simple--nákup-poklesu-od-vrcholu)
   - [2. Buy the Dip — Plný vstup při poklesu](#2-buy-the-dip--plný-vstup-při-poklesu)
   - [3. Scale-in — Průměrování do poklesu](#3-scale-in--průměrování-do-poklesu)
   - [4. Scale-in + Hold — Jádro vždy v trhu](#4-scale-in--hold--jádro-vždy-v-trhu)
   - [5. MACD Momentum — Signál hybnosti](#5-macd-momentum--signál-hybnosti)
   - [6. VIX Regime — Řízení strachu trhu](#6-vix-regime--řízení-strachu-trhu)
   - [7. Volatility Targeting — Konstantní riziko](#7-volatility-targeting--konstantní-riziko)
   - [8. Multi-Asset Rotation — Nejsilnější asset](#8-multi-asset-rotation--nejsilnější-asset)
   - [9. Dual Momentum — Hybnost s bezpečným přístavem](#9-dual-momentum--hybnost-s-bezpečným-přístavem)
   - [10. SMA Crossover — Trend s pásmem](#10-sma-crossover--trend-s-pásmem)
   - [11. ATR-SMA — Dynamické pásmo dle volatility](#11-atr-sma--dynamické-pásmo-dle-volatility)
4. [Porovnání strategií](#porovnání-strategií)
5. [Jak číst výsledky](#jak-číst-výsledky)
6. [Grid Search — hledání nejlepších parametrů](#grid-search--hledání-nejlepších-parametrů)

---

## Jak funguje backtesting

Backtesting znamená: *vezmi historická data a předstírej, že jsi obchodoval tehdy*.
Výsledkem je odpověď na otázku „kolik bych vydělal, kdybych tuto strategii používal v minulosti?".

**Základ:**
- Startovní kapitál: **10 000 $**
- Data: denní OHLCV (Open, High, Low, Close, Volume) z Yahoo Finance
- Výchozí perioda: posledních **5 let**
- Příkazy se vykonávají **druhý den ráno (Open)** po signálu — realističtěji než okamžitá cena v den signálu

**Co se měří:**
| Metrika | Co říká |
|---|---|
| **CAGR** | Průměrný roční výnos (v %) |
| **Max Drawdown** | Největší propad kapitálu od vrcholu (negativní = špatné) |
| **Win Rate** | Kolik obchodů skončilo v zisku |
| **Avg Trade Return** | Průměrný výnos jednoho obchodu |
| **Buy & Hold CAGR** | Co by vydělalo prosté „kup a drž" QQQ za stejnou dobu |

---

## Společné předpoklady

- **Bez poplatků a skluzu** — v reálu každý obchod stojí spread + komisi
- **Zlomkové akcie** — kapitál se dělí přesně, bez zaokrouhlování
- **Jeden ticker** (pokud není uvedeno jinak) — primárně QQQ
- **Žádný margin / páka** — pokud není explicitně povolena

---

## Strategie

---

### 1. Backtest Simple — Nákup poklesu od vrcholu
**Soubor:** `trading_algo_backtest_simple/backtest_qqq_v2.py`

#### Myšlenka
QQQ historicky po každém poklesu obnovuje svou hodnotu. Strategie hledá dočasné propady a vstupuje do nich — každý signál investuje malou část kapitálu (1 %), takže se opakující signály přirozeně průměrují.

#### Jak to funguje

```
Vstup:  Cena klesla ≥ 3 % od posledního vrcholu  →  kup zítra ráno za 1 % kapitálu
Výstup: Cena se vrátila zpět na úroveň vrcholu A zároveň je nad 30denní průměrnou cenou
```

**Vizualizace:**
```
Cena
 ▲
 │    ▲  ← Vrchol
 │   / \
 │  /   \  ← Pokles ≥ 3 % → VSTUP (1 % kapitálu)
 │ /     \  /‾‾‾‾‾
 │/       \/        ← Obnovení vrcholu + nad SMA30 → VÝSTUP
─────────────────────── čas
```

#### Parametry
- `drop_pct = 3 %` — minimální pokles pro vstup
- `alloc_pct = 1 %` — kolik procent kapitálu vložit na jeden signál
- `sma_window = 30` — délka klouzavého průměru pro potvrzení výstupu

#### Výstupy
- `equity_curve_v2.png` — vývoj kapitálu
- `price_with_trades_v2.png` — cenový graf se vstupy/výstupy a SMA30
- `trades_detail_v2.csv` — záznam každého obchodu

---

### 2. Buy the Dip — Plný vstup při poklesu
**Soubor:** `trading_algo_buy_the_dip/backtest_buy_the_dip.py`

#### Myšlenka
Stejný základ jako Backtest Simple, ale **celý volný kapitál** jde do každého obchodu najednou — přímočařejší přístup.

#### Jak to funguje

```
Vstup:  Cena klesla ≥ 5 % od posledního vrcholu  →  kup zítra ráno za 100 % dostupného kapitálu
Výstup: Cena se vrátila zpět na úroveň, ze které pokles začal  →  prodej na Close
```

**Klíčový rozdíl oproti Backtest Simple:**
- Investuje **vše najednou** (ne po 1 %)
- Výstup čistě na obnovení vrcholu (bez SMA podmínky)
- V trhu typicky jen 15–20 % času

#### Parametry (grid search)
- `drop_pct` — testovány hodnoty: 2 %, 3 %, 5 %, 7 %, 10 %, 15 %, 20 %

#### Výstupy
- `backtest_buy_the_dip.png` — 3 panely: cena + obchody, equity křivka, % v trhu
- `grid_search_results.csv` — výsledky pro různá `drop_pct`

---

### 3. Scale-in — Průměrování do poklesu
**Soubor:** `trading_algo_backtest_scalein/backtest_scalein_simple.py`

#### Myšlenka
Místo jednoho vstupu strategie **postupně přikupuje** jak cena klesá dál. Každé pásmo poklesu dostane část kapitálu — čím hlubší propad, tím více peněz jde do trhu. Průměrná nákupní cena se tím zlepšuje.

#### Jak to funguje

```
Definice pásem (příklad bin_size = 5 %):
  Pásmo 1: pokles 5 %  → alokuj 5 % kapitálu
  Pásmo 2: pokles 10 % → alokuj dalších 25 % kapitálu
  Pásmo 3: pokles 15 % → alokuj zbývajících 70 % kapitálu

Výstup: Cena překročí aktuální SMA  →  prodej vše
        NEBO pozice držena > max_hold_days  →  prodej
```

**Vizualizace:**
```
Cena
 ▲
 │    ▲ Vrchol
 │   / \
 │  /   ●── 5% pokles  → VSTUP 1 (5 % kapitálu)
 │ /     \
 │/       ●── 10% pokles → VSTUP 2 (25 % kapitálu)
 │         \
 │          ●── 15% pokles → VSTUP 3 (70 % kapitálu)
 │           \       /‾‾‾‾‾ (cena > SMA → VÝSTUP VŠE)
─────────────────────────────────── čas
```

#### Parametry
- `bin_size_pct` — šířka každého pásma (default 3 %)
- `max_drop_pct` — maximální pokles, který modelujeme (default 25 %)
- `initial_alloc_pct` — kolik alokovat do prvního pásma (default 5 %)
- `exit_sma_window` — délka SMA pro výstup (default 5)

#### Výstupy
- `backtest_scalein.png` — cena + SMA + vstupy, equity, % alokace v trhu

---

### 4. Scale-in + Hold — Jádro vždy v trhu
**Soubor:** `trading_algo_backtest_scalein_hold/backtest_scalein_hold.py`

#### Myšlenka
Hybridní přístup: **polovina kapitálu se nikdy neprodá** (pasivní jádro jako buy & hold), druhá polovina aktivně obchoduje pomocí scale-in logiky.

#### Jak to funguje

```
Jádro (hold_pct = 50 %):
  → Koupí se hned první den a drží navždy
  → Žádný výstupní signál

Satelit (zbývajících 50 %):
  → Stejná scale-in logika jako strategie č. 3
  → Přikupuje při poklesech, prodává na SMA signálu
```

#### Proč to dává smysl
- Jádro chrání před tím, že by strategie úplně minula silný trend (kdyby se scale-in část nikdy neinvestovala)
- Satelit zlepšuje průměrnou nákupní cenu v propadech
- Příklad výsledku: hold_pct=5 %, CAGR 16.89 % vs. buy & hold 14.58 %, max DD −29.56 %

#### Parametry
- `hold_pct` — kolik procent drží jádro (testováno 1–10 %)
- Zbytek jako Scale-in strategie

---

### 5. MACD Momentum — Signál hybnosti
**Soubor:** `trading_algo_macd_leverage/backtest_macd_leverage.py`

#### Myšlenka
MACD je klasický technický indikátor, který měří **hybnost trendu** (momentum). Strategie je v trhu, když hybnost zrychluje, a mimo trh, když zpomaluje.

#### Jak to funguje

```
Výpočet:
  MACD linie   = EMA(12) − EMA(26)    ← rozdíl dvou klouzavých průměrů
  Signal linie = EMA(9) z MACD linie  ← vyhlazení MACD linie
  Histogram    = MACD − Signal        ← síla a směr hybnosti

Vstup:  Histogram přejde z MINUSOVÝCH hodnot do PLUSOVÝCH  →  kup zítra ráno
Výstup: Histogram přejde z PLUSOVÝCH hodnot do MINUSOVÝCH  →  prodej zítra ráno
```

**Vizualizace histogramu:**
```
Histogram
   ▲
 + │ ██ ████      ← hybnost roste → jsme V TRHU
───┼──────────────── 0
 - │     ████     ← hybnost klesá → jsme MIMO TRH
   ▼
```

#### Páka (volitelně)
- Ticker `QQQ` = 1× (bez páky)
- Ticker `TQQQ` = 3× (třikrát pákový ETF, vyšší výnos i risk)

#### Parametry
- `fast_ema` — rychlý průměr (default 12)
- `slow_ema` — pomalý průměr (default 26)
- `signal_ema` — vyhlazení signálu (default 9)

---

### 6. VIX Regime — Řízení strachu trhu
**Soubor:** `trading_algo_vix_regime/backtest_vix_regime.py`

#### Myšlenka
VIX je „index strachu" — měří, jak moc jsou investoři nervózní. Když je strach vysoký, trhy jsou nestabilní. Strategie upravuje velikost pozice podle aktuálního VIX.

#### Jak to funguje

```
VIX < 20  (klid)      →  100 % v QQQ
VIX 20–30 (opatrnost) →   50 % v QQQ
VIX > 30  (panika)    →    0 % v QQQ (cash)

Přechod: vždy na Open druhého dne
```

**Vizualizace:**
```
VIX
 ▲
40│                 ████        ← panika → 0 % v trhu
30│─────────────────────────── horní práh
20│─────────────────────────── dolní práh
10│ ████████████                ← klid → 100 % v trhu
 ─────────────────────── čas
```

#### Parametry
- `vix_low` — dolní práh (default 20, testováno 15–25)
- `vix_high` — horní práh (default 30, testováno 25–40)

---

### 7. Volatility Targeting — Konstantní riziko
**Soubor:** `trading_algo_vol_targeting/backtest_vol_targeting.py`

#### Myšlenka
Namísto binárního „jsem/nejsem v trhu" strategie **průběžně škáluje velikost pozice** tak, aby roční volatilita portfolia zůstala přibližně konstantní (např. 15 %).

#### Jak to funguje

```
Každý den:
  Realizovaná volatilita = Klouzavá směrodatná odchylka výnosů × √252
  Cílová pozice (%)      = min(cílová_vol / realizovaná_vol, max_leverage)

Příklady:
  Trh je klidný (vol = 10 %)  →  pozice = 15/10 = 150 %  (omezeno na 100 %)
  Trh je bouřlivý (vol = 30 %) →  pozice = 15/30 = 50 %
```

**Intuice:** Když trh „křičí", zmenší se pozice. Když je ticho, zvětší se.

#### Parametry
- `target_vol` — cílová roční volatilita (default 15 %, testováno 10–40 %)
- `vol_window` — kolik dnů se používá k výpočtu aktuální volatility (default 20)
- `max_leverage` — strop pozice (default 100 %, lze zvýšit na 150 %)

---

### 8. Multi-Asset Rotation — Nejsilnější asset
**Soubor:** `trading_algo_multi_asset/backtest_multi_asset.py`

#### Myšlenka
Místo obchodování jednoho ETF strategie **drží vždy ten asset, který má největší hybnost** (momentum). Pokud žádný asset neroste, přesune vše do bezpečných dluhopisů (SHY).

#### Universe assetů
| Ticker | Co reprezentuje |
|---|---|
| **QQQ** | Nasdaq-100 (technologie) |
| **TLT** | Dlouhé americké dluhopisy |
| **GLD** | Zlato |
| **SHY** | Krátkodobé dluhopisy (cash ekvivalent) |

#### Jak to funguje

```
Každý den:
  1. Spočítej N-denní výnos každého rizikového assetu (QQQ, TLT, GLD)
  2. Nejlepší asset s POZITIVNÍM momentem → přesuň tam vše
  3. Pokud má NEJLEPŠÍ asset záporné momentum → přesuň do SHY

Přechod: prodej stávající asset na Open, kup nový na stejném Open
```

**Vizualizace:**
```
Čas:     Jan   Feb   Mar   Apr   May   Jun
Asset:  [QQQ] [QQQ] [TLT] [TLT] [SHY] [GLD]
         silný  │    dluh. │    strach  zlato
                rotace     rotace
```

#### Parametry
- `lookback` — jak daleko zpět se počítá momentum (default 126 dní = ~6 měsíců)

---

### 9. Dual Momentum — Hybnost s bezpečným přístavem
**Soubor:** `trading_algo_dual_momentum/backtest_dual_momentum.py`

#### Myšlenka
Rozšíření klasické Antonacciho strategie „Dual Momentum". Kombinuje **relativní momentum** (který asset je nejlepší) s **absolutním momentem** (je vůbec smysl být v trhu?).

#### Dva módy

**Mód 1 — Jednoduchý (QQQ vs. cash):**
```
Momentum QQQ > 0  →  drž QQQ
Momentum QQQ ≤ 0  →  jdi do cashe
```

**Mód 2 — Multi-asset (výchozí):**
```
Stejná logika jako Multi-Asset Rotation (strategie č. 8)
→ Relativní: vyber nejlepší z QQQ / TLT / GLD
→ Absolutní: pokud nejlepší má záporné momentum → SHY
```

#### Klíčový rozdíl od č. 8
Dual Momentum je flexibilní — umí běžet jako jednoduchá strategie (jen QQQ vs. cash) nebo jako plná rotace. Vhodné pro porovnávání.

#### Parametry
- `lookback` — perioda pro výpočet hybnosti (default 126 dní)

---

### 10. SMA Crossover — Trend s pásmem
**Soubor:** `trading_algo_sma_crossover/backtest_sma_crossover.py`

#### Myšlenka
Klasická trend-following strategie. Drž QQQ, dokud je cena nad klouzavým průměrem. Prodej, když cena klesne pod průměr. Pásmo (buffer) filtruje falešné signály při pohybu ceny kolem průměru.

#### Jak to funguje

```
Klouzavý průměr (SMA):  průměr posledních N zavíracích cen

Vstup:  Close > SMA × (1 + band)  →  kup zítra ráno
Výstup: Close < SMA × (1 − band)  →  prodej; rotuj do nejlepší alternativy (TLT/GLD/SHY)

Příklad (SMA200, band=1 %):
  SMA = 400 $
  Vstupní práh = 404 $ (+1 %)
  Výstupní práh = 396 $ (−1 %)
```

**Proč pásmo?**
Bez bufferu by cena oscilující kolem SMA generovala desítky falešných signálů. Pásmo vytvoří „mrtvou zónu" kolem průměru.

#### Asset rotace (volitelně)
- Při výstupu z QQQ strategie vybere nejlepší alternativu (TLT / GLD / SHY) podle krátkodobého momentu

#### Parametry
- `sma_window` — délka průměru (testováno 50–400, default 200)
- `band_pct` — šířka pásma (testováno 0–10 %, default 1 %)
- `alt_lookback` — lookback pro výběr alternativy (default 63 dní)

---

### 11. ATR-SMA — Dynamické pásmo dle volatility
**Soubor:** `trading_algo_atr_sma/backtest_atr_sma.py`

#### Myšlenka
Jako SMA Crossover, ale šířka pásma se **automaticky přizpůsobuje volatilitě trhu**. V klidném trhu je pásmo užší (citlivější), v bouřlivém wider (méně falešných signálů). K tomu se používá ATR (Average True Range).

#### Jak to funguje

```
ATR (Average True Range):
  True Range = max(High−Low, |High−PrevClose|, |Low−PrevClose|)
  ATR        = průměr True Range za N dní

Dynamické pásmo:
  band = (ATR / Close) × multiplier

Vstup:  Close > SMA × (1 + band)
Výstup: Close < SMA × (1 − band)
```

**Vizualizace:**
```
Cena
 ▲  ─ ─ ─ ─  Horní pásmo (SMA + ATR band) ← vstupní trigger
 │  ────────  SMA200
 │  ─ ─ ─ ─  Dolní pásmo (SMA − ATR band) ← výstupní trigger
 │
 │  Pozn.: pásma se rozšiřují při vysoké volatilitě
─────────────────────── čas
```

#### Klíčový rozdíl oproti SMA Crossover
- SMA Crossover: pevné pásmo (vždy ±1 %)
- ATR-SMA: **proměnné pásmo** — reaguje na skutečnou volatilitu trhu

#### Parametry
- `sma_window` — délka SMA (default 200)
- `atr_window` — délka ATR výpočtu (default 20)
- `atr_multiplier` — jak moc ATR zvětšit/zmenšit pásmo (default 1.0)

---

## Porovnání strategií

**Soubor:** `trading_algo_comparison/compare_strategies.py`

Meta-skript, který spustí všechny strategie s výchozími parametry najednou a vypíše tabulku:

```
python compare_strategies.py
```

Výstupy:
- Tabulka v terminálu: CAGR, Max DD, Win Rate, počet obchodů
- `comparison_equity.png` — sloupcový graf CAGR a Max Drawdown všech strategií vedle sebe

---

## Jak číst výsledky

**Příklad dobré strategie:**
```
CAGR:        18.5 %     ← vyšší než buy & hold (~14 % pro QQQ)
Max DD:      −22.0 %    ← menší propad než buy & hold (~−35 %)
Win Rate:     72 %      ← většina obchodů v zisku
Avg Return:  +3.1 %     ← průměrný obchod vydělal 3.1 %
```

**Na co dávat pozor:**
- **Overfitting** — pokud grid search najde CAGR 40 %, ale s velmi specifickými parametry, výsledek nemusí být robustní
- **Max Drawdown** — důležitější než CAGR; s −50 % drawdownem je těžké psychologicky vydržet
- **Buy & Hold benchmark** — dobrá strategie by měla překonat prostý nákup QQQ, nebo nabídnout výrazně nižší drawdown

---

## Grid Search — hledání nejlepších parametrů

Každá strategie obsahuje funkci `grid_search()`, která systematicky otestuje kombinace parametrů a seřadí je podle CAGR.

```bash
# Příklad spuštění grid search pro SMA Crossover
python backtest_sma_crossover.py  # → grid_search_results.csv
```

Výsledky jsou uloženy v `grid_search_results.csv` v příslušné složce. Vždy zkontroluj, zda nejlepší parametry dávají smysl i intuitivně — čísla mohou být zavádějící bez kontextu.
