"""Translates strategy signals into broker orders."""
from __future__ import annotations

import logging
from typing import Optional

from src.brokers.base_broker import BaseBroker, Order, OrderAction, OrderType, Position
from src.strategies.atr_sma_c import AtrSmaCStrategy
from src.strategies.base_strategy import Signal, SignalType

logger = logging.getLogger(__name__)


class SignalExecutor:
    """Converts a Signal list into live broker orders.

    Signals must be passed in execution order (SELL before BUY for rotation).
    For SELL signals the full current position is liquidated.
    For BUY signals the position size is calculated via the strategy.
    """

    def __init__(
        self,
        broker: BaseBroker,
        strategy: AtrSmaCStrategy,
        dry_run: bool = False,
    ) -> None:
        self._broker = broker
        self._strategy = strategy
        self._dry_run = dry_run

    def execute(
        self,
        signals: list[Signal],
        prices: dict[str, float],
    ) -> list[dict]:
        """Execute signals in order. Returns trade records for persistence."""
        if not signals:
            return []

        portfolio_value = self._broker.get_account_value()
        positions: dict[str, Position] = {
            p.symbol: p for p in self._broker.get_positions()
        }
        records: list[dict] = []

        for signal in signals:
            record = self._execute_one(signal, portfolio_value, prices, positions)
            if record:
                records.append(record)
                # Refresh state so subsequent BUYs use updated portfolio value
                portfolio_value = self._broker.get_account_value()
                positions = {p.symbol: p for p in self._broker.get_positions()}

        return records

    # ── Internal ───────────────────────────────────────────────────────────

    def _execute_one(
        self,
        signal: Signal,
        portfolio_value: float,
        prices: dict[str, float],
        positions: dict[str, Position],
    ) -> Optional[dict]:
        if signal.signal_type == SignalType.SELL:
            return self._sell(signal, prices, positions)
        return self._buy(signal, portfolio_value, prices)

    def _sell(
        self,
        signal: Signal,
        prices: dict[str, float],
        positions: dict[str, Position],
    ) -> Optional[dict]:
        pos = positions.get(signal.symbol)
        if pos is None or pos.quantity <= 0:
            logger.warning(
                "SELL signal for %s but no open position — skipped", signal.symbol
            )
            return None

        price = prices.get(signal.symbol) or pos.market_price
        order = Order(
            symbol=signal.symbol,
            action=OrderAction.SELL,
            quantity=pos.quantity,
            order_type=OrderType.MARKET,
        )
        return self._place(order, price, signal)

    def _buy(
        self,
        signal: Signal,
        portfolio_value: float,
        prices: dict[str, float],
    ) -> Optional[dict]:
        price = prices.get(signal.symbol)
        if not price or price <= 0:
            logger.error("No valid price for BUY %s — skipped", signal.symbol)
            return None

        pos_size = self._strategy.calculate_position_size(
            signal, portfolio_value, price
        )
        order = Order(
            symbol=signal.symbol,
            action=OrderAction.BUY,
            quantity=pos_size.quantity,
            order_type=OrderType.MARKET,
        )
        return self._place(order, price, signal)

    def _place(
        self, order: Order, price: float, signal: Signal
    ) -> Optional[dict]:
        record = {
            "symbol": order.symbol,
            "action": order.action.value,
            "quantity": order.quantity,
            "price": price,
            "reason": signal.metadata.get("reason", ""),
            "order_id": None,
        }

        if self._dry_run:
            logger.info("[DRY RUN] Would place: %s", order)
            return record

        order_id = self._broker.place_order(order)
        if order_id is None:
            logger.error("Order placement failed: %s", order)
            return None

        record["order_id"] = order_id
        logger.info("Executed %s  order_id=%s", order, order_id)
        return record
