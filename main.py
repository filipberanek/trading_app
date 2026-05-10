"""ATR-SMA-C Trading Bot — entry point.

Usage:
    python main.py --mode paper                # run scheduler (paper trading)
    python main.py --mode live                 # run scheduler (live — asks confirmation)
    python main.py --mode paper --run-once     # execute one cycle and exit
    python main.py --mode paper --dry-run      # one cycle, no real orders placed
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(os.getenv("LOG_PATH", "logs/trading.log")),
        ],
    )


def _confirm_live() -> None:
    print("\n" + "=" * 60)
    print("  ⚠️   LIVE TRADING MODE — real money will be used!")
    print("=" * 60)
    answer = input("Type 'yes' to confirm: ").strip().lower()
    if answer != "yes":
        print("Aborted.")
        sys.exit(0)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ATR-SMA-C Trading Bot")
    p.add_argument(
        "--mode",
        choices=["paper", "live"],
        default="paper",
        help="paper = IB Gateway port 4002 | live = port 4001 (default: paper)",
    )
    p.add_argument(
        "--config",
        default=os.getenv("CONFIG_PATH", "config/atr_sma_c.yaml"),
        help="Path to strategy YAML config",
    )
    p.add_argument(
        "--db",
        default=os.getenv("DB_PATH", "data/trading.db"),
        help="Path to SQLite database",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate signals but do not place any orders",
    )
    p.add_argument(
        "--run-once",
        action="store_true",
        help="Run exactly one cycle then exit (useful for cron / testing)",
    )
    p.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level (default: INFO)",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    os.makedirs("logs", exist_ok=True)
    _setup_logging(args.log_level)
    logger = logging.getLogger(__name__)

    if args.mode == "live" and not args.dry_run:
        _confirm_live()

    ibkr_port = int(
        os.getenv("IBKR_PORT", "4002" if args.mode == "paper" else "4001")
    )

    from src.engine.runner import TradingRunner
    from src.notifications.notifier import Notifier

    notifier = Notifier(
        telegram_token=os.getenv("TELEGRAM_TOKEN"),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        email_to=os.getenv("EMAIL_TO"),
        email_from=os.getenv("EMAIL_FROM"),
    )

    runner = TradingRunner(
        config_path=args.config,
        db_path=args.db,
        ibkr_host=os.getenv("IBKR_HOST", "127.0.0.1"),
        ibkr_port=ibkr_port,
        ibkr_client_id=int(os.getenv("IBKR_CLIENT_ID", "1")),
        trade_hour_utc=int(os.getenv("TRADE_HOUR_UTC", "8")),
        trade_minute_utc=int(os.getenv("TRADE_MINUTE_UTC", "5")),
        dry_run=args.dry_run,
        notifier=notifier,
    )

    logger.info(
        "Starting bot — mode=%s  dry_run=%s  run_once=%s",
        args.mode,
        args.dry_run,
        args.run_once,
    )

    if args.run_once or args.dry_run:
        runner.run_once()
    else:
        runner.start()


if __name__ == "__main__":
    main()
