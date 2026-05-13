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
        contract_specs: dict,
        dry_run: bool = False,
    ) -> None:
        self._broker = broker
        self._strategy = strategy
        self._contract_specs = contract_specs
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
        fx_rates = self._broker.get_fx_rates()
        positions: dict[str, Position] = {
            p.symbol: p for p in self._broker.get_positions()
        }
        records: list[dict] = []

        for signal in signals:
            record = self._execute_one(signal, portfolio_value, fx_rates, prices, positions)
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
        fx_rates: dict[str, float],
        prices: dict[str, float],
        positions: dict[str, Position],
    ) -> Optional[dict]:
        if signal.signal_type == SignalType.SELL:
            return self._sell(signal, prices, positions)
        return self._buy(signal, portfolio_value, fx_rates, prices)

    def _sell(
        self,
        signal: Signal,
        prices: dict[str, float],
        positions: dict[str, Position],
    ) -> Optional[dict]:
        pos = positions.get(signal.symbol)
        if pos is None or pos.quantity <= 0:
            raise RuntimeError(
                f"SELL signal for {signal.symbol} but no open position found — "
                f"position state is inconsistent, aborting cycle"
            )
        if signal.symbol not in prices:
            raise RuntimeError(
                f"No price for SELL {signal.symbol} — cannot record trade"
            )
        order = Order(
            symbol=signal.symbol,
            action=OrderAction.SELL,
            quantity=pos.quantity,
            order_type=OrderType.MARKET,
        )
        return self._place(order, prices[signal.symbol], signal)

    def _buy(
        self,
        signal: Signal,
        portfolio_value: float,
        fx_rates: dict[str, float],
        prices: dict[str, float],
    ) -> Optional[dict]:
        if signal.symbol not in prices:
            raise RuntimeError(
                f"No price available for BUY {signal.symbol} — cannot size position"
            )
        price_native = prices[signal.symbol]
        if price_native <= 0:
            raise RuntimeError(
                f"Price for {signal.symbol} is {price_native} — cannot size position"
            )

        if signal.symbol not in self._contract_specs:
            raise KeyError(
                f"No contract spec for '{signal.symbol}' — cannot determine currency for position sizing"
            )
        currency = self._contract_specs[signal.symbol]["currency"]
        if currency not in fx_rates:
            raise RuntimeError(
                f"FX rate for {currency} (required for {signal.symbol}) not found in IBKR account data — "
                f"available rates: {list(fx_rates.keys())}"
            )
        fx_rate = fx_rates[currency]
        price_usd = price_native * fx_rate

        pos_size = self._strategy.calculate_position_size(
            signal, portfolio_value, price_usd
        )
        quantity = int(pos_size.quantity)  # floor — no fractional shares on European ETFs
        if quantity <= 0:
            raise RuntimeError(
                f"Calculated quantity is 0 for BUY {signal.symbol} "
                f"(portfolio=${portfolio_value:.0f}, price={price_native:.4f} {currency} "
                f"= ${price_usd:.4f} USD) — aborting cycle"
            )
        logger.info(
            "BUY sizing: %s price=%.4f %s (=%.4f USD, fx=%.4f), portfolio=$%.0f → %d shares",
            signal.symbol, price_native, currency, price_usd, fx_rate, portfolio_value, quantity,
        )
        order = Order(
            symbol=signal.symbol,
            action=OrderAction.BUY,
            quantity=quantity,
            order_type=OrderType.MARKET,
        )
        return self._place(order, price_native, signal)

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
            raise RuntimeError(
                f"Order placement failed for {order} — broker returned no order ID"
            )

        record["order_id"] = order_id
        logger.info("Executed %s  order_id=%s", order, order_id)
        return record
