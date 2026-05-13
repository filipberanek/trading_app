# Deployment Instructions — ATR-SMA-C Trading Bot na Hetzner

> **Pro Clauda:** Tento dokument je průvodce nasazením trading bota na Hetzner server.
> Prováděj kroky postupně. Po každém kroku ověř výsledek před pokračováním.
> Pokud něco selže, zastav a řekni uživateli co přesně selhalo.

---

## Co budeme instalovat

- Ubuntu 22.04 server na Hetzner
- Docker + Docker Compose
- IB Gateway (headless IBKR přístup)
- Trading bot (2 kontejnery: engine + dashboard)
- Firewall + základní zabezpečení
- Systemd pro auto-start po restartu serveru

---

## ČÁST 1 — Hetzner server

### 1.1 Objednat server

Jdi na [hetzner.com](https://www.hetzner.com/cloud) → Cloud → Add Server.

Doporučená konfigurace:
| Parametr | Hodnota |
|---|---|
| Location | Nuremberg nebo Falkenstein (EU) |
| Image | **Ubuntu 22.04** |
| Type | **CX21** (2 vCPU, 4 GB RAM) — postačí |
| SSH Key | Přidej svůj veřejný klíč (viz níže) |
| Name | `trading-bot` |

**Jak přidat SSH klíč (pokud ještě nemáš):**
Na svém lokálním počítači (ne na serveru):
```bash
# Vygenerovat klíč (pokud ještě neexistuje)
ssh-keygen -t ed25519 -C "trading-bot"

# Zobrazit veřejný klíč — tento text zkopíruj do Hetzner
cat ~/.ssh/id_ed25519.pub
```

Po vytvoření serveru si poznač jeho **IP adresu** (např. `65.21.xxx.xxx`).

---

## ČÁST 2 — Připojení a základní nastavení serveru

### 2.1 Připojit se přes SSH

Na lokálním počítači:
```bash
ssh root@<IP_SERVERU>
```

Očekávaný výsledek: uvítací zpráva Ubuntu, prompt `root@trading-bot:~#`

### 2.2 Aktualizovat systém

```bash
apt update && apt upgrade -y
```

Může trvat 1–2 minuty.

### 2.3 Vytvořit neprivilegovaného uživatele

```bash
adduser trader
usermod -aG sudo trader
mkdir -p /home/trader/.ssh
cp /root/.ssh/authorized_keys /home/trader/.ssh/
chown -R trader:trader /home/trader/.ssh
chmod 700 /home/trader/.ssh
chmod 600 /home/trader/.ssh/authorized_keys
```

### 2.4 Zabezpečit SSH (zakázat přihlášení jako root)

```bash
sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd
```

**Ověření — otevři nový terminál a zkus:**
```bash
ssh trader@<IP_SERVERU>
```
Musí se připojit. Teprve potom zavři původní root session.

### 2.5 Nastavit firewall (UFW)

```bash
ufw allow OpenSSH
ufw allow 8501/tcp    # Streamlit dashboard
ufw --force enable
ufw status
```

Očekávaný výstup:
```
Status: active
To                Action  From
--                ------  ----
OpenSSH           ALLOW   Anywhere
8501/tcp          ALLOW   Anywhere
```

### 2.6 Nainstalovat fail2ban (ochrana proti brute force)

```bash
apt install -y fail2ban
systemctl enable fail2ban
systemctl start fail2ban
```

---

## ČÁST 3 — Instalace Dockeru

```bash
apt install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Přidat uživatele `trader` do skupiny docker:
```bash
usermod -aG docker trader
```

**Ověření:**
```bash
docker --version
docker compose version
```

Očekávaný výstup: verze Docker (23+) a Docker Compose (2+).

---

## ČÁST 4 — Nahrát kód na server

Proveď na **lokálním počítači** (ne na serveru):

```bash
# Z adresáře projektu trading_app
rsync -av \
  --exclude='.git' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  ./ trader@<IP_SERVERU>:/root/trading_app/
```

**Ověření na serveru:**
```bash
ssh trader@<IP_SERVERU>
ls /root/trading_app/
```

Musíš vidět: `src/`, `config/`, `main.py`, `docker-compose.yml`, `Dockerfile` atd.

---

## ČÁST 5 — Konfigurace

### 5.1 Vytvořit .env soubor

Na serveru:
```bash
cd /root/trading_app
cp .env.example .env
nano .env
```

Vyplnit tyto hodnoty (ostatní můžou zůstat jako default):

```bash
# IB Gateway — bude běžet jako Docker kontejner na stejném serveru
IBKR_HOST=ibgateway         # název Docker služby, ne IP
IBKR_PORT=4002              # 4002 = paper, 4001 = live
IBKR_CLIENT_ID=1

# Čas spuštění strategie (UTC)
TRADE_HOUR_UTC=8
TRADE_MINUTE_UTC=5

# Telegram notifikace
TELEGRAM_TOKEN=<tvůj_token>
TELEGRAM_CHAT_ID=<tvůj_chat_id>

# Email (volitelné)
# SMTP_HOST=smtp.gmail.com
# SMTP_PASSWORD=<app_password>
# EMAIL_TO=<tvůj@email.cz>
```

Uložit: `Ctrl+O`, `Enter`, `Ctrl+X`

### 5.2 Nastavit oprávnění

```bash
chmod 600 /root/trading_app/.env
chown -R trader:trader /root/trading_app/
mkdir -p /root/trading_app/data /root/trading_app/logs
```

### 5.3 Ověřit contract specs

Otevřít `config/atr_sma_c.yaml` a zkontrolovat `exchange` + `currency` pro každý ticker:
```bash
nano /root/trading_app/config/atr_sma_c.yaml
```

Pro ověření správnosti kontraktů použij IBKR Symbol Search:
`https://www.interactivebrokers.com/en/trading/symbol-search.php`

---

## ČÁST 6 — IB Gateway

IB Gateway je aplikace od IBKR která umožňuje API přístup. Musí být přihlášena pomocí IBKR credentials.

### 6.1 Přidat IB Gateway do docker-compose.yml

```bash
nano /root/trading_app/docker-compose.yml
```

Přidat službu `ibgateway` (zkopírovat přesně):

```yaml
  ibgateway:
    image: ghcr.io/gnzsnz/ib-gateway:latest
    container_name: ibgateway
    restart: unless-stopped
    environment:
      TWS_USERID: ${IBKR_USERNAME}
      TWS_PASSWORD: ${IBKR_PASSWORD}
      TRADING_MODE: ${IBKR_TRADING_MODE:-paper}
      TWS_SETTINGS_PATH: /home/ibgateway/Jts
      VNC_SERVER_PASSWORD: ${VNC_PASSWORD:-changeme}
    volumes:
      - ibgateway_config:/home/ibgateway/Jts
    networks:
      - private
    ports:
      - "5900:5900"    # VNC pro vzdálenou správu (volitelné)
```

A přidat volume na konec souboru:
```yaml
volumes:
  trading_data:
  ibgateway_config:     # přidat tento řádek
```

### 6.2 Přidat IBKR credentials do .env

```bash
nano /root/trading_app/.env
```

Přidat:
```bash
IBKR_USERNAME=<tvůj_ibkr_login>
IBKR_PASSWORD=<tvůj_ibkr_heslo>
IBKR_TRADING_MODE=paper    # paper nebo live
VNC_PASSWORD=<zvolte_heslo_pro_vnc>
```

> ⚠️ Toto jsou přihlašovací údaje k IBKR. Soubor `.env` nesmí nikdy opustit server.

---

## ČÁST 7 — Spuštění

### 7.1 Build a spuštění

```bash
cd /root/trading_app
docker compose up -d --build
```

První build trvá 3–5 minut (stahování base image a instalace Python závislostí).

### 7.2 Zkontrolovat stav kontejnerů

```bash
docker compose ps
```

Očekávaný výstup — všechny kontejnery `running`:
```
NAME                 STATUS
ibgateway            running
trading_engine       running
trading_dashboard    running
```

### 7.3 Zkontrolovat logy

```bash
# Trading engine
docker logs -f trading_engine

# IB Gateway
docker logs -f ibgateway
```

V logu trading_engine hledej:
```
TradingRunner ready — mode=paper  trade_time=08:05 UTC
Scheduler started — sleeping until next trigger
```

V logu ibgateway hledej:
```
IB Gateway started
```

### 7.4 Otestovat dashboard

Otevřít v prohlížeči: `http://<IP_SERVERU>:8501`

Musí se zobrazit Streamlit dashboard.

---

## ČÁST 8 — Ověření spojení s IBKR

### 8.1 Spustit dry-run (žádné reálné objednávky)

```bash
docker exec trading_engine python main.py --mode paper --dry-run
```

Hledej v logu:
- `Connected to IBKR Gateway` — spojení OK
- `Fetched X bars for EQQQ` — data OK
- `[DRY RUN] Would place: ...` — signál by byl vykonán
- nebo `Signals: none (hold)` — žádný signál dnes

Pokud uvidíš `Cannot connect to IBKR broker` → viz sekci Troubleshooting níže.

---

## ČÁST 9 — Auto-start po restartu serveru (systemd)

### 9.1 Vytvořit systemd service

```bash
nano /etc/systemd/system/trading.service
```

Vložit:
```ini
[Unit]
Description=ATR-SMA-C Trading Bot
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=trader
WorkingDirectory=/root/trading_app
ExecStart=docker compose up
ExecStop=docker compose down
Restart=always
RestartSec=15

[Install]
WantedBy=multi-user.target
```

### 9.2 Aktivovat service

```bash
systemctl daemon-reload
systemctl enable trading
systemctl start trading
systemctl status trading
```

Očekávaný výstup: `Active: active (running)`

### 9.3 Ověřit restart

```bash
reboot
```

Po restartu (počkej 60 sekund):
```bash
ssh trader@<IP_SERVERU>
docker compose -f /root/trading_app/docker-compose.yml ps
```

Všechny kontejnery musí být `running` bez ručního zásahu.

---

## ČÁST 10 — Ověření notifikací

### 10.1 Test Telegram

```bash
docker exec trading_engine python -c "
import os
from dotenv import load_dotenv
load_dotenv()
from src.notifications.notifier import Notifier
n = Notifier(
    telegram_token=os.getenv('TELEGRAM_TOKEN'),
    telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID'),
)
n.send('Test z trading serveru', 'Pokud vidíš tuto zprávu, notifikace fungují!', level='INFO')
print('Odesláno')
"
```

Musíš dostat zprávu do Telegramu do 10 sekund.

---

## Troubleshooting

### `Cannot connect to IBKR broker`

1. Zkontroluj logy IB Gateway: `docker logs ibgateway`
2. Ověř, že `IBKR_HOST=ibgateway` v `.env` (název Docker služby, ne IP)
3. Ověř credentials: `docker exec ibgateway env | grep TWS`
4. IB Gateway se po přihlášení může ptát na 2FA — přihlásit se přes VNC:
   ```
   # Na lokálním počítači nainstaluj VNC viewer a připoj se na:
   <IP_SERVERU>:5900
   # Heslo: hodnota VNC_PASSWORD z .env
   ```

### `No data for EQQQ — aborting`

1. Zkontroluj contract specs v `config/atr_sma_c.yaml`
2. Ověř na IBKR Symbol Search že ticker/exchange/currency souhlasí
3. Zkontroluj, zda IBKR účet má přístup k danému trhu (market data subscription)

### Dashboard se nenačte (`http://<IP>:8501` nefunguje)

1. `ufw status` — ověř že port 8501 je otevřený
2. `docker logs trading_dashboard` — hledej chyby
3. `docker compose ps` — ověř že kontejner běží

### Kontejner se neustále restartuje

```bash
docker logs --tail=50 trading_engine
```
Hledej `Error` nebo `Exception` na konci logu.

---

## Užitečné příkazy

```bash
# Zobrazit logy v reálném čase
docker logs -f trading_engine

# Restartovat jen engine (po úpravě kódu)
docker compose restart trading

# Rebuild po úpravě kódu (nahrát nový kód přes rsync, pak:)
docker compose up -d --build trading

# Zobrazit aktuální stav DB
docker exec trading_engine sqlite3 data/trading.db \
  "SELECT ts, status, message FROM heartbeat ORDER BY id DESC LIMIT 5;"

# Zobrazit poslední obchody
docker exec trading_engine sqlite3 data/trading.db \
  "SELECT ts, symbol, action, quantity, price FROM trades ORDER BY id DESC LIMIT 10;"

# Ruční spuštění jednoho cyklu (bez scheduleru)
docker exec trading_engine python main.py --mode paper --run-once

# Zastavit vše
docker compose down
```

---

## Checklist před ostrým (live) obchodováním

- [ ] Paper trading běží alespoň 2 týdny bez chyb
- [ ] Heartbeat v dashboardu je `OK` každých 5 minut
- [ ] Telegram notifikace dorazily při testu
- [ ] Dry-run úspěšně projde (`--dry-run`)
- [ ] Pozice v IBKR paper účtu odpovídají DB (`trades` tabulka)
- [ ] Server přežil restart a vše nastartovalo automaticky
- [ ] `.env` soubor je `chmod 600` a není v gitu
- [ ] Změnit `IBKR_TRADING_MODE=live` a `IBKR_PORT=4001` v `.env`
- [ ] Spustit s `--mode live` a potvrdit `yes`
