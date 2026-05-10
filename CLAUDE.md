# Trading Bot – IBKR Automatický Obchodní Systém

## ⚠️ KRITICKÉ UPOZORNĚNÍ
Tento projekt pracuje s **reálnými financemi**. Každá chyba může znamenat finanční ztrátu.
- **NIKDY** nespouštěj neotestovaný kód na live účtu
- **VŽDY** testuj nejdříve na Paper Trading účtu
- **VŽDY** piš testy před implementací logiky (TDD)
- **VŽDY** ověř výsledky manuálně před každým nasazením
- Při jakékoliv nejistotě **ZASTAV a zeptej se**

---

## Architektura projektu

```
trading-bot/
├── src/
│   ├── brokers/        # Připojení k brokerům (IBKR)
│   ├── strategies/     # Obchodní strategie
│   ├── engine/         # Produkční smyčka (runner, scheduler, state_writer)
│   ├── data/           # Zpracování tržních dat
│   └── utils/          # Sdílené utility
├── tests/              # Testy (zrcadlí strukturu src/)
├── experiments/        # Experimenty strategií (není v produkci)
├── config/             # Konfigurace (NIKDY necommituj .env!)
├── logs/               # Logy (gitignored)
├── dashboard.py        # Streamlit dashboard (pouze čte z DB)
└── main.py             # Entry point
```

---

## Produkční architektura (Hetzner)

Systém je rozdělen do dvou striktně oddělených částí. **Nikdy je nemíchej.**

```
INTERNET
   │
   ▼
┌──────────────────────────────────┐
│          Hetzner Server          │
│                                  │
│  [Trading Engine]  private net   │
│   - ib_insync + strategie        │──► IBKR (pouze outbound)
│   - IBKR credentials (.env)      │
│   - žádný exposed port           │
│        │ write only              │
│  [PostgreSQL]      private net   │
│   - user: trader (rw)            │
│   - user: viewer (ro)            │
│        │ read only               │
│  [Frontend]     private+public   │
│   - Streamlit dashboard          │──► 443 → prohlížeč
│   - pouze read-only DB přístup   │
│   - ŽÁDNÉ IBKR credentials       │
└──────────────────────────────────┘
```

### Klíčová bezpečnostní pravidla
- Trading Engine nemá žádný inbound port — ani SSH z internetu
- Frontend **nikdy** nesmí obsahovat IBKR credentials ani přímé spojení na IBKR
- DB má dva uživatele: `trader` (INSERT/UPDATE/SELECT) a `viewer` (SELECT only)
- Všechny credentials pouze v `.env`, nikdy v kódu ani v gitu
- Tok dat je jednosměrný: Trading Engine → DB → Frontend

### Produkční stack
- **Orchestrace:** Docker Compose + systemd (restart při pádu / bootu)
- **IBKR:** IB Gateway (headless, pro servery) — ne TWS
- **DB:** PostgreSQL (produkce), SQLite pouze lokálně při vývoji
- **Hlavní smyčka:** `src/engine/runner.py` — spouští se v tržní hodiny, zapisuje heartbeat

### Klíčové DB tabulky
```
positions   – aktuální pozice (symbol, qty, avg_price)
trades      – každý vykonaný obchod
portfolio   – denní snapshot (date, cash, equity, total)
heartbeat   – timestamp posledního běhu (monitoring živosti)
signals     – vygenerované signály
```

---

## Stack
- **Python** 3.12+
- **Broker API:** ib_insync
- **Dashboard:** Streamlit + Plotly (read-only, čte z DB)
- **Databáze:** SQLite (vývoj), PostgreSQL (produkce)
- **Kontejnerizace:** Docker Compose
- **Testy:** pytest
- **Linting:** flake8, black

---

## Coding Standards

### PEP8 – Vždy dodržovat
- Max délka řádku: **88 znaků** (black standard)
- Docstringy pro každou třídu a metodu
- Type hints povinné pro všechny funkce
- Žádné magické konstanty – vše do `config/`

### DRY (Don't Repeat Yourself)
- Sdílená logika patří do `src/utils/`
- Žádné copy-paste kódu – vždy refaktoruj do funkce/třídy
- Konfigurace na jednom místě

### KISS (Keep It Simple, Stupid)
- Preferuj jednoduché řešení před složitým
- Nepřidávej abstrakce, dokud nejsou skutečně potřeba
- Kratší a čitelnější kód > chytrý a komplikovaný kód

### OOP Principy
- Každá strategie je třída dědící z `BaseStrategy`
- Každý broker je třída dědící z `BaseBroker`
- Používej dataclasses pro datové struktury
- Dependency injection místo globálních proměnných

### Bezpečnost
- Přihlašovací údaje **POUZE** v `.env` souboru
- `.env` je v `.gitignore` – **NIKDY** ho necommituj
- Žádné hardcoded IP adresy, porty ani hesla v kódu

---

## Testování

### Povinné testy
- Unit testy pro každou strategii
- Mock IBKR připojení pro testy (nikdy živé připojení v testech!)
- Testy pro edge cases: prázdná data, chyba připojení, nulový zůstatek

### Spuštění testů
```bash
pytest tests/ -v --cov=src
```

### Před každým commitem
```bash
black src/ tests/
flake8 src/ tests/
pytest tests/ -v
```

---

## Git Workflow

### Větve
- `main` – pouze stabilní, otestovaný kód
- `develop` – aktivní vývoj
- `feature/nazev-featury` – nové funkce
- `hotfix/popis` – urgentní opravy

### Commit zprávy (Czech nebo English, konzistentně)
```
feat: přidána nová strategie RSI
fix: oprava výpočtu pozice při short sellu
test: testy pro OrderManager
refactor: extrakce logiky do BaseStrategy
```

### Zakázáno commitovat
- `.env` soubory
- `logs/` složku
- `__pycache__/`
- Přihlašovací údaje kdekoliv

---

## Příkazy pro vývoj

```bash
# Instalace závislostí
pip install -r requirements.txt

# Spuštění testů
pytest tests/ -v

# Formátování kódu
black src/ tests/

# Kontrola kódu
flake8 src/ tests/

# Spuštění dashboardu
streamlit run dashboard.py

# Spuštění bota (paper trading)
python main.py --mode paper
```
