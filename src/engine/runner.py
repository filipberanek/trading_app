"""Main trading loop — one evaluation cycle per trading day.

Schedule:  weekdays at TRADE_HOUR_UTC:TRADE_MINUTE_UTC (default 08:05 UTC).
Execution: market order shortly after European market open (09:05 CET = 08:05 UTC).

Flow per cycle:
  1. Connect to IBKR
  2. Fetch OHLCV for all tickers
  3. Determine current position
  4. Generate signals via AtrSmaCStrategy
  5. Execute orders (SELL then BUY)
  6. Persist state to DB + send notifications
  7. Disconnect
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import yaml

from src.brokers.ibkr_broker import IBKRBroker
from src.engine.data_fetcher import DataFetcher
from src.engine.executor import SignalExecutor
from src.engine.state_db import StateDB
from src.notifications.notifier import Notifier
from src.strategies.atr_sma_c import CASH, AtrSmaCStrategy, MarketSnapshot

logger = logging.getLogger(__name__)


class TradingRunner:
    """Orchestrates the full daily trading cycle."""

    # Liveness heartbeat interval (independent of trade cycles)
    _HEARTBEAT_INTERVAL_S: int = 300        # every 5 minutes
    # How many consecutive IB Gateway failures before sending an alert
    _ALERT_AFTER_FAILURES: int = 2          # alert after ~10 min of downtime

    def __init__(
        self,
        config_path: str = "config/atr_sma_c.yaml",
        db_path: str = "data/trading.db",
        ibkr_host: str = "127.0.0.1",
        ibkr_port: int = 4002,
        ibkr_client_id: int = 1,
        trade_hour_utc: int = 8,
        trade_minute_utc: int = 5,
        dry_run: bool = False,
        notifier: Optional[Notifier] = None,
    ) -> None:
        with open(config_path) as fh:
            cfg = yaml.safe_load(fh)

        params = {**cfg["parameters"], "main_ticker": cfg["universe"]["main_ticker"]}
        self._strategy = AtrSmaCStrategy(params)
        self._main_ticker: str = cfg["universe"]["main_ticker"]
        self._alt_tickers: list[str] = cfg["universe"]["alt_tickers"]
        self._safe_ticker: Optional[str] = cfg["universe"].get("safe_ticker")
        if "contracts" not in cfg:
            raise KeyError(
                "Missing 'contracts' section in config — all tickers must have explicit contract specs"
            )
        self._contract_specs: dict = cfg["contracts"]

        self._broker = IBKRBroker(ibkr_host, ibkr_port, ibkr_client_id, self._contract_specs)
        self._db = StateDB(db_path)
        self._notifier = notifier or Notifier()  # no-op if unconfigured
        self._dry_run = dry_run
        self._trade_hour = trade_hour_utc
        self._trade_minute = trade_minute_utc
        self._consecutive_failures = 0

        logger.info(
            "TradingRunner ready — mode=%s  trade_time=%02d:%02d UTC  dry_run=%s",
            "paper" if ibkr_port == 4002 else "live",
            trade_hour_utc,
            trade_minute_utc,
            dry_run,
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Blocking scheduler loop.

        - Runs run_once() on each scheduled weekday.
        - Writes a liveness heartbeat every 5 minutes.
        - Sends a notification after 2 consecutive IB Gateway failures (~10 min).
        """
        logger.info("Scheduler started — sleeping until next trigger")
        last_heartbeat = 0.0

        while True:
            now = datetime.now(tz=timezone.utc)

            if self._is_trigger_time(now):
                self._safe_run_once()
                last_heartbeat = time.monotonic()

            if time.monotonic() - last_heartbeat >= self._HEARTBEAT_INTERVAL_S:
                self._liveness_check()
                last_heartbeat = time.monotonic()

            time.sleep(30)

    def run_once(self) -> None:
        """Single cycle: connect → evaluate → execute → persist → disconnect.

        Raises on connection failure. Suitable for manual / cron invocation.
        """
        logger.info("=== Cycle start ===")
        if not self._broker.connect():
            raise RuntimeError("Cannot connect to IBKR broker")
        try:
            fetcher = DataFetcher(self._broker.ib, self._contract_specs)
            self._cycle(fetcher)
        finally:
            self._broker.disconnect()
        logger.info("=== Cycle complete ===")

    # ── Scheduler helpers ──────────────────────────────────────────────────

    def _liveness_check(self) -> None:
        """Ping IB Gateway; accumulate failures and alert after threshold."""
        alive = self._check_ibkr_alive()
        if alive:
            self._consecutive_failures = 0
            self._db.write_heartbeat("OK")
        else:
            self._consecutive_failures += 1
            self._db.write_heartbeat("ERROR", "IB Gateway unreachable")
            logger.warning(
                "IB Gateway unreachable (failure #%d)", self._consecutive_failures
            )
            if self._consecutive_failures == self._ALERT_AFTER_FAILURES:
                self._notifier.send_error(
                    "IB Gateway unreachable",
                    f"Trading engine cannot connect to IB Gateway.\n"
                    f"Consecutive failures: {self._consecutive_failures} "
                    f"(~{self._consecutive_failures * self._HEARTBEAT_INTERVAL_S // 60} min).\n"
                    f"Check that IB Gateway is running and logged in.",
                )

    def _check_ibkr_alive(self) -> bool:
        """Lightweight connect/disconnect probe."""
        try:
            ok = self._broker.connect()
            if ok:
                self._broker.disconnect()
            return ok
        except Exception as exc:
            logger.warning("IB Gateway probe failed: %s", exc)
            return False

    def _is_trigger_time(self, now: datetime) -> bool:
        if now.weekday() >= 5:      # Saturday / Sunday
            return False
        return now.hour == self._trade_hour and now.minute == self._trade_minute

    def _safe_run_once(self) -> None:
        try:
            self.run_once()
            self._consecutive_failures = 0
            self._db.write_heartbeat("OK")
        except Exception as exc:
            logger.exception("Cycle failed: %s", exc)
            self._db.write_heartbeat("ERROR", str(exc))
            self._notifier.send_error(
                "Trading cycle failed",
                f"Error: {exc}\n\nCheck logs for details.",
            )
        time.sleep(90)  # prevent double-firing within the same minute

    # ── Core cycle ─────────────────────────────────────────────────────────

    def _cycle(self, fetcher: DataFetcher) -> None:
        all_tickers = (
            [self._main_ticker]
            + self._alt_tickers
            + ([self._safe_ticker] if self._safe_ticker else [])
        )

        # 1. Fetch OHLCV
        ohlcv: dict = {}
        for ticker in all_tickers:
            df = fetcher.get_ohlcv(ticker, bars=200)
            if df is not None:
                ohlcv[ticker] = df
            else:
                logger.warning("No data for %s — skipped", ticker)

        if self._main_ticker not in ohlcv:
            msg = f"No data for main ticker {self._main_ticker} — aborting cycle"
            logger.error(msg)
            self._db.write_heartbeat("ERROR", msg)
            self._notifier.send_error("Data fetch failed", msg)
            return

        # 2. Determine current position
        positions = self._broker.get_positions()
        held = {p.symbol for p in positions if p.quantity > 0}
        if held:
            current_position = (
                self._main_ticker if self._main_ticker in held else next(iter(held))
            )
        else:
            current_position = CASH
        logger.info("Current position: %s", current_position)

        # 3. Generate signals
        snapshot = MarketSnapshot(
            main_ohlcv=ohlcv[self._main_ticker],
            alt_ohlcv={t: ohlcv[t] for t in self._alt_tickers if t in ohlcv},
            current_position=current_position,
        )
        signals = self._strategy.generate_signals(snapshot)
        logger.info("Signals: %s", signals or "none (hold)")
        self._db.write_signals(signals, executed=bool(signals))

        if not signals:
            self._db.write_portfolio(self._broker.get_account_value())
            return

        # 4. Price map (last close as sizing estimate for market orders)
        prices = {
            ticker: float(df["Close"].iloc[-1]) for ticker, df in ohlcv.items()
        }

        # 5. Execute
        executor = SignalExecutor(self._broker, self._strategy, self._contract_specs, dry_run=self._dry_run)
        records = executor.execute(signals, prices)

        # 6. Persist + notify
        portfolio_value = self._broker.get_account_value()
        for r in records:
            self._db.write_trade(
                symbol=r["symbol"],
                action=r["action"],
                quantity=r["quantity"],
                price=r.get("price"),
                portfolio_value=portfolio_value,
                ibkr_order_id=str(r["order_id"]) if r.get("order_id") else None,
                reason=r.get("reason", ""),
            )
            self._notifier.send_trade(
                f"{r['action']} {r['symbol']}",
                f"Qty:    {r['quantity']:.4f}\n"
                f"Price:  {r.get('price', '?')}\n"
                f"Reason: {r.get('reason', '')}\n"
                f"Portfolio value: {portfolio_value:,.2f}",
            )

        self._db.write_positions(self._broker.get_positions())
        self._db.write_portfolio(portfolio_value)
