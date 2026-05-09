# Top strategie – detailní popis

> Zdroj parametrů: `trading_algo_comparison/comparison_ml_20260425_1606.txt`  
> Walk-forward test: Train 2017-03-23 – 2023-03-22 | Test 2023-03-23 – 2026-04-24  
> Universum aktiv při rotaci: EQQQ, IUES, IGLN, IDTL, IBZL, EEA, IUCS, SEGA

## Aktiva používaná při rotaci

### Riziková aktiva (do nich se rotuje při pozitivním momentu)
| Ticker | Název | Co to je |
|--------|-------|-----------|
| **EQQQ** | Invesco NASDAQ-100 UCITS ETF | Sleduje 100 největších nefinančních firem na NASDAQ – technologicky zaměřený, hlavní aktivum portfolia |
| **IUES** | iShares S&P 500 Energy Sector UCITS ETF | Energetický sektor USA – ropné a plynárenské firmy (ExxonMobil, Chevron); dobře si vede při inflaci a vysokých cenách energií |
| **IGLN** | iShares Physical Gold ETC | Fyzické zlato – bezpečný přístav při geopolitické nejistotě a inflaci; korelace s akciemi je nízká |
| ~~IDTL~~ | ~~iShares $ Treasury Bond 20+yr UCITS ETF~~ | ~~Odstraněno z rotace~~ – dluhopisy jako rotační aktivum zhoršují výsledky v inflačním prostředí (2022). Zůstávají pouze jako safe haven (SEGA). |
| **IBZL** | iShares MSCI Brazil UCITS ETF | Brazilský akciový trh – rozvíjející se trh s vysokým potenciálem i rizikem; komoditně orientovaný |
| **EEA** | iShares MSCI Eastern Europe ex-Russia UCITS ETF | Akcie z východní Evropy (bez Ruska) – Polsko, Česko, Maďarsko; rozvíjející se trh |
| **IUCS** | iShares S&P 500 Consumer Staples Sector UCITS ETF | Defensivní spotřební zboží USA (P&G, Coca-Cola, Walmart) – drží hodnotu i v recesích |

### Bezpečné aktivum (útočiště při negativním momentu nebo panice)
| Ticker | Název | Co to je |
|--------|-------|-----------|
| **SEGA** | iShares Core Euro Government Bond UCITS ETF | Státní dluhopisy eurozóny – sem strategie přesune kapitál, když žádné rizikové aktivum nemá kladné momentum. V normálních podmínkách má nízkou volatilitu a mírný výnos. |

> **Poznámka:** V roce 2022 SEGA jako safe haven prodělala −270 EUR (36 dní celkem) kvůli agresivnímu zdražování ECB. Experimenty s CASH jako safe haven (nulový výnos) ukázaly horší celkové výsledky – grid search s CASH volí kratší lookback, který generuje příliš mnoho whipsawů v bull marketu. SEGA jako safe haven zůstává optimální volbou.

---

## Výsledky na out-of-sample (TEST) datech

| Strategie   | CAGR   | Max Drawdown | Win Rate | Uzavřené obchody |
|-------------|--------|-------------|----------|-----------------|
| **VolTgt**  | 24.70% | -24.40%     | N/A      | 0 (denní rebalance) |
| **ATR-SMA** | 19.70% | -16.20%     | 70%      | 10               |
| **MultiAsset** | 17.50% | -20.40%  | 57.5%    | 127              |
| **DualMom** | 17.50% | -20.40%     | 57.5%    | 127              |
| **SMACross**| 10.70% | -18.00%     | 60%      | 10               |
| **VIX**     | 7.10%  | -29.20%     | 48%      | 25               |
| Buy&Hold    | 24.50% | -26.90%     | N/A      | 0 (benchmark)    |

---

## 1. MultiAsset (Asset Rotation)

### Co to je?
Rotační strategie, která každý den vyhodnotí, který aktiv měl nejlepší výkonnost za posledních N dní (momentum), a přesune 100 % kapitálu do tohoto aktiva. Pokud žádné rizikové aktivum neroste, přesune se do bezpečného aktiva (dluhopisy/cash).

### Jak přesně funguje?
1. Každý den vypočítá **N-denní momentum** pro každé aktivum: `momentum = cena_dnes / cena_před_N_dny - 1`
2. **Relativní momentum** – vybere aktivum s nejvyšším N-denním výnosem ze skupiny rizikových aktiv
3. **Absolutní momentum** – pokud má i vítěz negativní momentum (trh celkově klesá), přejde do **SEGA** (dluhopisy jako defenzivní útočiště)
4. Když se vybrané aktivum změní, prodá stávající pozici a koupí nové aktivum při **příštím otevření trhu**

### Klíčová myšlenka
Trhy mají tendenci pokračovat v nastoleném trendu (momentum efekt). Strategie vždy „sedí" na aktuálně nejsilnějším aktivu a vyhýbá se slabým.

### Nejlepší parametry (z train dat)
```
lookback = 21 dní
```
- `lookback` – počet dní pro výpočet zpětného výnosu (momentum okno); 21 dní ≈ 1 obchodní měsíc

---

## 2. DualMom (Dual Momentum)

### Co to je?
Rozšíření klasického Dual Momentum (Gary Antonacci). Kombinuje momentumovou rotaci aktiv s filtrem na základě úrovně strachu na trhu (VIX index). Přidává vrstvu tržního režimu: při vysokém VIX přechází do bezpečnějších pozic agresivněji.

### Jak přesně funguje?
1. Stejný základ jako MultiAsset – **relativní + absolutní momentum** pro výběr aktiva
2. Navíc sleduje **VIX index** (index volatility = míra strachu na trhu):
   - VIX < `vix_low` → trh je klidný, drž rizikové aktivum normálně
   - VIX > `vix_high` → trh je v panice, přesuň se do **SEGA**
   - VIX mezi prahy → neutrální zóna, drž 50 % pozice
3. Signál se vyhodnotí denně, obchod se provede při **příštím otevření trhu**

### Klíčová myšlenka
Dual momentum samo o sobě může reagovat pomalu. VIX filtr přidává rychlý „záchranný mechanismus" – když trh explicitně signalizuje paniku, strategie to zachytí okamžitě bez čekání na momentumový signál.

### Nejlepší parametry (z train dat)
```
vix_low  = 25
vix_high = 40
```
- `vix_low` – pod touto hodnotou VIX je trh klidný → plná alokace do vybraného aktiva
- `vix_high` – nad touto hodnotou VIX je trh v panické prodejní vlně → přesun do bezpečí

---

## 3. VIX (VIX Regime + Volatility Targeting)

### Co to je?
Strategie kombinující tržní režim (detekce přes VIX) s cílením na konkrétní úroveň volatility portfolia. Nesnaží se předpovědět směr trhu, ale udržet **stabilní rizikový profil** přes čas.

### Jak přesně funguje?
1. Každý den vypočítá **realizovanou volatilitu** za posledních `vol_window` dní (standardní odchylka denních výnosů × √252)
2. Určí cílovou velikost pozice: `pozice = target_vol / realizovaná_vol`
3. Výsledek se ořízne na `[0, max_leverage]` – nikdy nepáčí víc než je povoleno
4. Když volatilita roste (trh je nervóznější) → **automaticky zmenší pozici**
5. Když volatilita klesá (klidný trh) → **automaticky zvětší pozici**
6. Pozice se nastaví vždy na základě **včerejší volatility** (aby nedocházelo k look-ahead bias)

### Klíčová myšlenka
Většina strategií ztrácí peníze proto, že v krizích drží příliš velkou pozici. VolTgt/VIX to řeší mechanicky – čím více trh hází, tím menší díl kapitálu je vystaven riziku.

### Nejlepší parametry (z train dat)
```
target_vol   = 0.35 (35 % anualizovaná volatilita)
vol_window   = 2 dní
max_leverage = 1.0  (bez páky)
```
- `target_vol` – cílová roční volatilita portfolia; 0.35 je poměrně agresivní (odpovídá volatilitě akcií)
- `vol_window` – počet dní pro výpočet realizované volatility; 2 dny = velmi rychlá reakce na změny
- `max_leverage` – maximální povolená páka; 1.0 = bez páky (max 100 % investováno)

---

## 4. VolTgt (Volatility Targeting)

### Co to je?
Čistá verze volatility targetingu bez VIX filtru. Mechanicky škáluje velikost pozice každý den tak, aby portfolio mělo přibližně konstantní riziko vyjádřené volatilitou.

### Jak přesně funguje?
1. Sleduje jeden aktivum (hlavní index/ETF)
2. Denně přepočítá realizovanou volatilitu za `lookback` dní
3. Nastaví pozici: `pozice = target_vol / realizovaná_vol` (oříznutá na rozsah `[0, max_leverage]`)
4. **Neexistují žádné explicitní nákupní/prodejní signály** – je to čistě mechanické denní přebalancování
5. Strategický výnos: `výnos = pozice × výnos_aktiva`

### Klíčová myšlenka
Jednoduchost je síla. Bez složitých podmínek jen udržuje stabilní volatilitu portfolia. Historicky funguje dobře, protože volatilita je **mean-reverting** (vrací se k průměru) a **persistentní** v krátkém horizontu.

### Nejlepší parametry (z train dat)
```
lookback = 21 dní
```
- `lookback` – počet dní pro výpočet rolling volatility; 21 dní = 1 měsíc (dobrý kompromis mezi rychlostí reakce a stabilitou)

---

## 5. SMACross (EMA Crossover)

### Co to je?
Trend-following strategie na bázi kříže klouzavých průměrů (Moving Average Crossover). Kupuje, když krátkodobý průměr překříží dlouhodobý průměr zdola nahoru (trendový signál), a prodává při opačném kříži.

### Jak přesně funguje?
1. Denně počítá **tři exponenciální klouzavé průměry (EMA)**:
   - `fast_ema` – rychlá EMA (krátkodobý trend)
   - `slow_ema` – pomalá EMA (dlouhodobý trend)
   - `signal_ema` – signální EMA (vyhlazení rozdílu fast a slow)
2. **Nákupní signál:** fast_ema překříží slow_ema zdola → vstup do dlouhé pozice (100 % investováno)
3. **Prodejní signál:** fast_ema překříží slow_ema seshora → výstup (přechod do cash nebo alternativního aktiva)
4. `signal_ema` funguje jako filtr pro snížení falešných signálů (podobně jako MACD signální linie)
5. Obchod se provede při **příštím otevření trhu** po signálu

### Klíčová myšlenka
EMA křížení patří k nejstarším technickým indikátorům. Výhoda: chytí velké trendy. Nevýhoda: v bočním trhu generuje mnoho falešných signálů (whipsaws). Proto je `slow_ema` nastavena relativně vysoko (45 dní).

### Nejlepší parametry (z train dat)
```
fast_ema   = 12 dní
slow_ema   = 45 dní
signal_ema = 12 dní
```
- `fast_ema` – rychlá EMA sledující krátkodobý momentum; 12 dní je standardní volba (podobně jako MACD)
- `slow_ema` – pomalá EMA definující hlavní trend; 45 dní filtruje krátkodobý šum
- `signal_ema` – EMA aplikovaná na rozdíl fast/slow pro generování čistějších signálů; 12 dní = rychlá reakce

---

## Srovnání strategií

| Strategie   | Typ signálu       | Frekvence obchodů | Pozicování           | Safe haven |
|-------------|-------------------|-------------------|----------------------|------------|
| MultiAsset  | Momentum rotace   | Nízká (při změně) | Binární (100%)       | SEGA (dluhopisy EU) |
| DualMom     | Momentum + VIX    | Nízká (při změně) | Binární (100%)       | SEGA (dluhopisy EU) |
| VIX/VolTgt  | Žádný (rebalance) | Denní             | Kontinuální (0–100%) | N/A (škáluje pozici)|
| SMACross    | EMA křížení       | Střední           | Binární (100%)       | SEGA (dluhopisy EU) |

> **Poznámka:** DualMom a MultiAsset dosáhly identického CAGR (17.5 %) a identických výsledků na test datech – sdílejí stejnou rotační logiku, DualMom přidává VIX filtr který v tomto období nepřidal hodnotu. VolTgt dosáhl nejvyššího CAGR (24.7 %) a je těsně za Buy&Hold benchmarkem (24.5 %) při lepším drawdownu.
