# Dual Momentum & Multi-Asset Rotation — detailní popis

Obě strategie jsou implementací **Antonacciho Dual Momentum** (kniha *Dual Momentum Investing*, 2014).
Liší se pouze tím, kolik aktiv porovnávají a zda umí přepnout do „cash" vs. konkrétní bezpečné aktivum.

---

## 1. Co je Dual Momentum

Dual Momentum kombinuje dva druhy hybnosti:

| Typ | Co měří | Otázka |
|---|---|---|
| **Relativní momentum** | Výkon jednoho aktiva vůči ostatním | *Které aktivum bylo nejsilnější?* |
| **Absolutní momentum** | Výkon aktiva vůči sobě samému (vs. nula) | *Bylo vůbec v plusu?* |

Kombinace zabraňuje tomu, aby strategie kupovala „nejméně špatné" aktivum v medvědím trhu — pokud je i to nejlepší aktivum v mínusu, přesune se do bezpečné hodnoty.

---

## 2. Vzorec pro momentum

```
momentum[t] = close[t] / close[t - lookback] - 1
```

- **`lookback`** je počet obchodních dní zpět (výchozí: 126 = ~6 měsíců)
- Výsledkem je prosté procentuální zhodnocení za dané období
- Výpočet probíhá **každý obchodní den** — signál se tedy aktualizuje denně

---

## 3. Pravidla výběru aktiva

```
1. Spočítej momentum pro každé rizikové aktivum (QQQ, TLT, GLD)
2. Najdi to s nejvyšším momentem → "nejlepší rizikové aktivum"
3. Je momentum tohoto aktiva > 0?
      ANO → kup "nejlepší rizikové aktivum"
      NE  → kup bezpečné aktivum (SHY / SEGA)
```

### Příklad

| Aktivum | Momentum (126 dní) |
|---|---|
| QQQ | +8 % |
| TLT | +3 % |
| GLD | -2 % |
| → nejlepší: **QQQ** | momentum > 0 → **kupujeme QQQ** |

| Aktivum | Momentum (126 dní) |
|---|---|
| QQQ | -5 % |
| TLT | -1 % |
| GLD | -8 % |
| → nejlepší: **TLT** | momentum < 0 → **kupujeme SHY** (safe asset) |

---

## 4. Warmup perioda

- Prvních `lookback` obchodních dní **se neobchoduje** — nestačí dat pro výpočet
- Při `lookback=126` to je přibližně prvních 6 měsíců dat
- Equity křivka existuje od prvního dne, ale je plochá (hotovost)

---

## 5. Exekuce obchodů

### Timing — kdy se obchod provede

```
Den t   → spočítám momentum, zjistím cílové aktivum
Den t+1 → prodám stávající aktivum za Open, koupím nové za Open
```

Strategie **nikdy neobchoduje na Close dne t** — obchod se provede vždy na **Open následujícího dne**. Tím se simuluje realistické chování: signál se generuje po zavření trhu, příkaz se podá před otevřením dalšího dne.

### Co se stane při přepnutí aktiva

```python
# Prodej starého aktiva
exit_price = opens[current_asset][t+1]
cash = shares * exit_price

# Koupě nového aktiva (ze stejné hotovosti, na stejném Open)
buy_price = opens[target][t+1]
shares = cash / buy_price
```

- Prodej a nákup probíhají **na stejný den** (t+1), ale každý za své vlastní Open
- Výsledkem je jeden obchod: exit z A + entry do B = **1 rotace = 1 closed trade**
- **Žádná transakční poplatky** nejsou v backtestingu zahrnuty

---

## 6. Vstup a výstup — přesná pravidla

| Událost | Podmínka | Akce |
|---|---|---|
| **Vstup** | cílové aktivum se změnilo (target ≠ current) | kup target za Open[t+1] |
| **Výstup** | cílové aktivum se změnilo | prodej current za Open[t+1] |
| **Žádná akce** | target == current | nic, drž pozici |

Strategie je **vždy investovaná** — buď v rizikovém aktivu, nebo v bezpečném. Nikdy není v „čisté hotovosti" (po warmup perioda).

---

## 7. Stop loss

**Žádný stop loss neexistuje.**

Strategie vystupuje z pozice **výhradně** na základě změny momentového signálu. Pokud se trh prudce propadne, ale momentum na konci dne stále ukazuje na stejné aktivum, strategie drží a čeká na příští signál.

To je záměrné: Antonacci tvrdí, že momentum samo o sobě funguje jako „přirozený stop loss" — propad se musí projevit v momentu, načež proběhne rotace do bezpečného aktiva.

---

## 8. Pozicování — velikost pozice

- Vždy **100 % kapitálu** v jednom aktivu
- Bez páky
- Zlomkové akcie jsou povoleny (backtest neomezuje na celé kusy)

---

## 9. Počítání obchodů (win rate, počet rotací)

Každá **rotace** (přepnutí z A do B) se zaznamená jako jeden uzavřený obchod:

```
trade = {
    asset:        aktivum, které bylo prodáno
    entry_date:   den, kdy bylo koupeno
    entry_price:  Open v den koupě
    exit_date:    den, kdy bylo prodáno
    exit_price:   Open v den prodeje
    pnl:          zisk/ztráta = shares * (exit_price - entry_price)
    held_days:    počet obchodních dní, po které bylo aktivum drženo
}
```

**Win rate** = podíl rotací, kde `pnl > 0` (tedy výstupní cena > vstupní cena).

### Proč může být hodně obchodů

Při krátkém lookbacku (např. 21 dní) se momentum mění rychle → signál přepíná frequently → hodně rotací. Při dlouhém lookbacku (252 dní = 1 rok) se momentum mění pomalu → méně rotací. Grid search hledá optimální lookback.

Přibližné vodítko:
| Lookback | Typický počet rotací za 9 let |
|---|---|
| 21 dní | 50–150 |
| 63 dní | 20–60 |
| 126 dní | 10–30 |
| 252 dní | 5–15 |

---

## 10. Dual Momentum vs. Multi-Asset — co je stejné a co se liší

### V `compare_strategies.py` jsou obě strategie prakticky totožné

```python
# DualMom (compare_strategies.py řádek ~201):
run_backtest_dual_momentum(dfs=raw_multi, risky_assets=RISKY_ASSETS,
                            safe_asset=SAFE_ASSET, **dual_momentum_params)

# MultiAsset (compare_strategies.py řádek ~217):
run_backtest_multi_asset(dfs=raw_multi, risky_assets=RISKY_ASSETS,
                          safe_asset=SAFE_ASSET, **multi_asset_params)
```

Obě dostávají **stejná data, stejné aktivum universe, stejný safe asset**.  
Algoritmus uvnitř (`select_asset`, momentumový výpočet, entry/exit logika) je **kód-pro-kód identický**.

**Jediný možný rozdíl: parametr `lookback`.**  
Grid search optimalizuje lookback pro každou strategii zvlášť — DualMom může najít `lookback=63`, MultiAsset `lookback=126`. Jiný lookback → jiná frekvence rotací → jiné výsledky. Pokud grid search dá oběma stejný lookback, výstupy jsou **bit-for-bit identické**.

Důvod mít obě v porovnání: otestovat, zda volba lookbacku výrazně mění výsledky. Slouží jako citlivostní test.

---

### Kdy se DualMom od MultiAsset skutečně liší

`backtest_dual_momentum.py` má navíc **single-asset mód** (aktivuje se když `dfs=None`):

| | Multi-asset mód (`dfs` zadán) | Single-asset mód (`dfs=None`) |
|---|---|---|
| Universe | N rizikových aktiv + 1 safe | Jediné aktivum (QQQ) |
| Kdy do cash | best_momentum ≤ 0 | momentum ≤ 0 |
| Exit exekuce | Open[t+1] | **Close[t]** (jiné!) |
| Entry exekuce | Open[t+1] | Open[t+1] |
| Použito v compare | ✅ (multi-asset mód) | ❌ |

Single-asset mód je výrazně odlišná strategie — obchoduje pouze jeden ticker a jde do čisté hotovosti (ne do safe asset). V `compare_strategies.py` se **nepoužívá**, je tam pouze jako backward-compatible fallback pro standalone spuštění souboru.

---

## 11. Co strategie neumí

- **Žádná diverzifikace uvnitř periody** — 100 % v jednom aktivu, bez rebalancování
- **Žádné stop lossy** — v prudkém propadu může ztratit i 20–30 % předtím, než momentum reaguje
- **Žádný pákovací efekt** — výnos je omezen na výkon zvoleného aktiva
- **Citlivost na lookback** — různé hodnoty lookback dávají velmi rozdílné výsledky, proto je nutný grid search
- **Lag** — momentum je zpožděný indikátor; signál se generuje, až když propad/růst je dostatečně velký a dostatečně dlouhý

---

## 12. Shrnutí průběhu jednoho obchodu (příklad)

```
Pondělí 14. 1.:
  → výpočet 126denního momentum
  → QQQ: +12%, TLT: +2%, GLD: -3%
  → relativní max: QQQ, absolutní: > 0
  → target = QQQ
  → aktuálně držíme TLT → ZMĚNA → trigger

Úterý 15. 1. (Open):
  → prodej TLT @ 98.50 EUR
  → nákup QQQ @ 420.00 EUR
  → trade TLT uzavřen: entry 95.00, exit 98.50, pnl = +3.5 EUR/akcii

Středa 16. 1. – …:
  → momentum se přepočítává každý den
  → target stále = QQQ → žádná akce, držíme

Pátek 21. 3.:
  → momentum: QQQ: -1%, TLT: +5%, GLD: +8%
  → relativní max: GLD, absolutní: > 0
  → target = GLD, aktuálně QQQ → ZMĚNA → trigger

Pondělí 24. 3. (Open):
  → prodej QQQ @ 415.00 EUR (ztráta oproti 420.00)
  → nákup GLD @ 185.00 EUR
  → trade QQQ uzavřen: entry 420.00, exit 415.00, pnl = -5 EUR/akcii
```
