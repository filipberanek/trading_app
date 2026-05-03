"""
Interactive Brokers broker implementation using ib_insync.
"""

import logging
from typing import Optional

from ib_insync import IB, Contract, MarketOrder, LimitOrder, Stock

from src.brokers.base_broker import BaseBroker, Order, OrderAction, OrderType, Position

logger = logging.getLogger(__name__)


class IBKRBroker(BaseBroker):
    """
    Interactive Brokers implementation of BaseBroker.

    Uses ib_insync library to communicate with IB Gateway.

    Example:
        broker = IBKRBroker(host='127.0.0.1', port=4002, client_id=1)
        if broker.connect():
            positions = broker.get_positions()
    """

    def __init__(self, host: str, port: int, client_id: int) -> None:
        super().__init__(host, port, client_id)
        self._ib = IB()

    def connect(self) -> bool:
        """Connect to IB Gateway."""
        try:
            self._ib.connect(self.host, self.port, clientId=self.client_id)
            self._is_connected = True
            logger.info(
                f"Connected to IBKR Gateway at {self.host}:{self.port} "
                f"(clientId={self.client_id})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IBKR Gateway: {e}")
            self._is_connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from IB Gateway."""
        self._ib.disconnect()
        self._is_connected = False
        logger.info("Disconnected from IBKR Gateway.")

    def place_order(self, order: Order) -> Optional[int]:
        """Place an order via IB Gateway."""
        if not self._is_connected:
            logger.error("Cannot place order: not connected to broker.")
            return None
        try:
            contract = self._create_contract(order.symbol)
            ib_order = self._create_ib_order(order)
            trade = self._ib.placeOrder(contract, ib_order)
            order_id = trade.order.orderId
            logger.info(f"Order placed: {order} -> orderId={order_id}")
            return order_id
        except Exception as e:
            logger.error(f"Failed to place order {order}: {e}")
            return None

    def cancel_order(self, order_id: int) -> bool:
        """Cancel an existing order."""
        try:
            open_orders = self._ib.openOrders()
            for o in open_orders:
                if o.orderId == order_id:
                    self._ib.cancelOrder(o)
                    logger.info(f"Order {order_id} cancelled.")
                    return True
            logger.warning(f"Order {order_id} not found in open orders.")
            return False
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_positions(self) -> list[Position]:
        """Get all current open positions."""
        try:
            raw_positions = self._ib.positions()
            positions = [
                Position(
                    symbol=p.contract.symbol,
                    quantity=p.position,
                    average_cost=p.avgCost,
                    market_price=0.0,  # Updated separately via market data
                )
                for p in raw_positions
            ]
            logger.debug(f"Retrieved {len(positions)} positions.")
            return positions
        except Exception as e:
            logger.error(f"Failed to retrieve positions: {e}")
            return []

    def get_account_value(self) -> float:
        """Get total net liquidation value of the account."""
        try:
            account_values = self._ib.accountValues()
            for av in account_values:
                if av.tag == "NetLiquidation" and av.currency == "USD":
                    value = float(av.value)
                    logger.debug(f"Account value: ${value:,.2f}")
                    return value
            logger.warning("NetLiquidation value not found in account data.")
            return 0.0
        except Exception as e:
            logger.error(f"Failed to retrieve account value: {e}")
            return 0.0

    def _create_contract(self, symbol: str) -> Contract:
        """Create an IBKR Stock contract for a given symbol."""
        contract = Stock(symbol, "SMART", "USD")
        self._ib.qualifyContracts(contract)
        return contract

    def _create_ib_order(self, order: Order):
        """Convert an Order object to an ib_insync order."""
        action = order.action.value
        if order.order_type == OrderType.MARKET:
            return MarketOrder(action, order.quantity)
        elif order.order_type == OrderType.LIMIT:
            if order.limit_price is None:
                raise ValueError("Limit price required for LIMIT orders.")
            return LimitOrder(action, order.quantity, order.limit_price)
        else:
            raise NotImplementedError(
                f"Order type {order.order_type} not yet implemented."
            )
