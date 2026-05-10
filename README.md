# ATR-SMA-C Trading Bot

Automatický obchodní systém postavený na strategii **ATR-SMA-C** (ATR-band SMA trend-following s rotací do nejsilnějšího alternativního ETF nebo cashe).

---

## Jak strategie funguje

```
Každý obchodní den v 09:05 CET:

  1. Načte OHLCV data z IBKR (posledních 200 denních barů)
  2. Spočítá SMA(15) a ATR(14) pro EQQQ
  3. band = ATR / Close * 0.3

  Pokud drží EQQQ a Close < SMA * (1 - band):
    → SELL EQQQ
    → BUY alt s nejvyšším (Close - SMA) / ATR > 0
    → pokud žádný alt nesplňuje podmínku → zůstane v cashe

  Pokud není v EQQQ a Close > SMA * (1 + band):
    → SELL stávající pozici (pokud existuje)
    → BUY EQQQ

  Jinak → drží, nic nedělá
```

Parametry byly vybrány pomocí stability-based K-fold cross-validace (score = avg/std CAGR přes train roky).  
Výsledky na OOS (2023–2026): **CAGR 25.2 %, Max Drawdown −12.8 %** vs Buy&Hold 24.5 % / −26.9 %.

---

## Architektura

```
main.py                      ← CLI entry point
src/
├── strategies/
│   └── atr_sma_c.py         ← čistá signal logika (bez brokera)
├── brokers/
│   └── ibkr_broker.py       ← IBKR wrapper (ib_insync)
└── engine/
    ├── data_fetcher.py       ← OHLCV z IBKR historical data
    ├── executor.py           ← Signal → Order → IBKR
    ├── state_db.py           ← SQLite persistence
    └── runner.py             ← hlavní smyčka (scheduler)
config/
└── atr_sma_c.yaml           ← parametry strategie + contract specs
data/
└── trading.db               ← SQLite DB (auto-created)
logs/
└── trading.log              ← log soubor (auto-created)
```

---

## Požadavky

- Python 3.12+
- IB Gateway (doporučeno) nebo TWS
- Účet u Interactive Brokers (paper nebo live)

---

## Lokální spuštění (bez Dockeru)

### 1. Naklonovat a nainstalovat závislosti

```bash
git clone <repo>
cd trading_app
pip install -r requirements.txt
```

### 2. Vytvořit `.env` soubor

```bash
cp .env.example .env
# Upravit .env — minimálně IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID
```

### 3. Spustit IB Gateway

Stáhnout z [interactivebrokers.com](https://www.interactivebrokers.com/en/trading/ibgateway.php).

Nastavení IB Gateway:
- **Mode:** Paper Trading (pro testování) nebo Live Trading
- **Port:** 4002 (paper) nebo 4001 (live)
- **API → Settings:** Enable ActiveX and Socket Clients ✓
- **Trusted IP:** 127.0.0.1

### 4. Ověřit contract specs

Otevřít [IBKR Symbol Search](https://www.interactivebrokers.com/en/trading/symbol-search.php)  
a ověřit `exchange` a `currency` pro každý ticker v `config/atr_sma_c.yaml`.

### 5. Spustit bot

```bash
# Paper trading — jeden cyklus (testování)
python main.py --mode paper --run-once

# Paper trading — dry run (žádné objednávky, jen logy)
python main.py --mode paper --dry-run

# Paper trading — scheduler (spustí se každý pracovní den v 08:05 UTC)
python main.py --mode paper

# Live trading — vyžádá potvrzení
python main.py --mode live
```

### 6. Spustit dashboard

```bash
streamlit run dashboard.py
# Otevřít: http://localhost:8501
```

---

## Produkční nasazení na Hetzner (Docker)

### 1. Nahrát kód na server

```bash
rsync -av --exclude='.git' --exclude='data/' --exclude='logs/' \
  ./ user@<server-ip>:/opt/trading_app/
```

### 2. Vytvořit `.env` na serveru

```bash
ssh user@<server-ip>
cd /opt/trading_app
cp .env.example .env
nano .env   # vyplnit IBKR_HOST atd.
```

### 3. Spustit Docker Compose

```bash
docker compose up -d --build
```

Kontejnery:
| Kontejner | Co dělá | Porty |
|---|---|---|
| `trading_engine` | Obchodní bot (scheduler) | žádné — nelze dosáhnout z internetu |
| `trading_dashboard` | Streamlit monitoring | 8501 |

### 4. Zkontrolovat logy

```bash
docker logs -f trading_engine
docker logs -f trading_dashboard
```

### 5. Spustit při startu serveru (systemd)

```bash
# /etc/systemd/system/trading.service
[Unit]
Description=ATR-SMA-C Trading Bot
After=docker.service
Requires=docker.service

[Service]
WorkingDirectory=/opt/trading_app
ExecStart=docker compose up
ExecStop=docker compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
systemctl enable trading
systemctl start trading
```

### 6. IB Gateway na serveru

IB Gateway musí běžet na stejném serveru (nebo na dostupném hostu). Doporučená Docker image:

```yaml
# Přidat do docker-compose.yml
  ibgateway:
    image: ghcr.io/gnzsnz/ib-gateway:latest
    container_name: ibgateway
    restart: unless-stopped
    environment:
      TWS_USERID: ${IBKR_USERNAME}
      TWS_PASSWORD: ${IBKR_PASSWORD}
      TRADING_MODE: paper   # nebo 'live'
    networks:
      - private
```

Pak nastavit `IBKR_HOST=ibgateway` a `IBKR_PORT=4002` v `.env`.

---

## Konfigurace

### `config/atr_sma_c.yaml`

```yaml
parameters:
  sma_window: 15       # SMA lookback (dny)
  atr_window: 14       # ATR lookback (dny)
  atr_multiplier: 0.3  # šířka pásma

universe:
  main_ticker: EQQQ
  alt_tickers: [IUES, IGLN, IBZL, EEA, IUCS]
  safe_ticker: SEGA

contracts:
  EQQQ:
    sec_type: ETF
    exchange: LSE      # ← ověřit v IBKR Symbol Search
    currency: USD
  # ...
```

### Proměnné prostředí (`.env`)

| Proměnná | Popis | Default |
|---|---|---|
| `IBKR_HOST` | IP adresa IB Gateway | `127.0.0.1` |
| `IBKR_PORT` | Port IB Gateway | `4002` (paper) / `4001` (live) |
| `IBKR_CLIENT_ID` | Client ID spojení | `1` |
| `TRADE_HOUR_UTC` | Hodina spuštění (UTC) | `8` |
| `TRADE_MINUTE_UTC` | Minuta spuštění (UTC) | `5` |
| `DB_PATH` | Cesta k SQLite souboru | `data/trading.db` |
| `LOG_LEVEL` | Úroveň logování | `INFO` |

---

## REST API

Spuštění: `uvicorn src.api.main:app --port 8000`

| Endpoint | Popis |
|---|---|
| `GET /api/status` | Živost enginu (heartbeat, věk v minutách) |
| `GET /api/positions` | Aktuální pozice |
| `GET /api/equity?days=365` | Historie hodnoty portfolia |
| `GET /api/trades?limit=100` | Vykonané obchody |
| `GET /api/signals?limit=50` | Vygenerované signály |

---

## Testování

```bash
# Všechny testy
pytest tests/ -v

# Pouze testy strategie
pytest tests/strategies/ -v

# Dry run (jeden cyklus, žádné reálné objednávky)
python main.py --mode paper --dry-run
```

### Před nasazením na live

1. `pytest tests/ -v` — všechny testy musí projít
2. `python main.py --mode paper --run-once` — otestovat s paper účtem
3. Zkontrolovat logy a DB (`data/trading.db`)
4. Ověřit, že pozice v IBKR odpovídají stavu v DB

---

## Databáze

SQLite soubor: `data/trading.db`

| Tabulka | Obsah |
|---|---|
| `heartbeat` | Timestamp každého cyklu + status (OK/ERROR) |
| `positions` | Snapshot pozic po každém cyklu |
| `trades` | Každý vykonaný obchod (symbol, akce, qty, cena) |
| `portfolio` | Denní hodnota portfolia (pro equity křivku) |
| `signals` | Vygenerované signály (i ty, na které nebylo reagováno) |

Prohlížení:
```bash
sqlite3 data/trading.db "SELECT * FROM trades ORDER BY id DESC LIMIT 10;"
sqlite3 data/trading.db "SELECT * FROM heartbeat ORDER BY id DESC LIMIT 5;"
```

---

## ⚠️ Bezpečnostní pravidla

- **NIKDY** nenasazuj na live bez předchozího paper trading testu
- **NIKDY** necommituj `.env` do gitu
- Dashboard kontejner má **read-only** přístup k DB — nemůže psát příkazy
- Trading engine nemá **žádný exposed port** — není dostupný z internetu
- IBKR credentials jsou **pouze** v `.env` souboru na serveru
