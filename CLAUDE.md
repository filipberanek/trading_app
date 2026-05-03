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
│   ├── data/           # Zpracování tržních dat
│   └── utils/          # Sdílené utility
├── tests/              # Testy (zrcadlí strukturu src/)
├── experiment/         # Experimenty různých strategií, které ještě nejsou v produkci
├── config/             # Konfigurace (NIKDY necommituj .env!)
├── logs/               # Logy (gitignored)
├── dashboard.py        # Streamlit dashboard
└── main.py             # Entry point
```

## Stack
- **Python** 3.12+
- **Broker API:** ib_insync
- **Dashboard:** Streamlit + Plotly
- **Databáze:** SQLite (vývoj), PostgreSQL (produkce)
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
