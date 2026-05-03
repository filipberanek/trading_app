"""
Base broker abstract class for all broker integrations.

All broker implementations must inherit from this class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Supported order types."""

    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP LMT"


class OrderAction(Enum):
    """Order actions."""

    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    """Represents a trading order."""

    symbol: str
    action: OrderAction
    quantity: float
    order_type: OrderType
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None

    def __repr__(self) -> str:
        return (
            f"Order({self.action.value} {self.quantity} {self.symbol} "
            f"@ {self.order_type.value})"
        )


@dataclass
class Position:
    """Represents an open position."""

    symbol: str
    quantity: float
    average_cost: float
    market_price: float

    @property
    def market_value(self) -> float:
        """Current market value of the position."""
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return (self.market_price - self.average_cost) * self.quantity

    def __repr__(self) -> str:
        return (
            f"Position({self.symbol}, qty={self.quantity}, "
            f"cost={self.average_cost:.2f}, pnl={self.unrealized_pnl:.2f})"
        )


class BaseBroker(ABC):
    """
    Abstract base class for all broker integrations.

    Implementations must handle:
    - Connection management and reconnection
    - Order placement and cancellation
    - Position and account data retrieval
    - Error handling for all API calls
    """

    def __init__(self, host: str, port: int, client_id: int) -> None:
        """
        Initialize broker connection parameters.

        Args:
            host: Broker API host address.
            port: Broker API port.
            client_id: Unique client ID for this connection.
        """
        self.host = host
        self.port = port
        self.client_id = client_id
        self._is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the broker.

        Returns:
            True if connection successful, False otherwise.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the broker."""

    @abstractmethod
    def place_order(self, order: Order) -> Optional[int]:
        """
        Place an order with the broker.

        Args:
            order: Order to place.

        Returns:
            Order ID if successful, None if failed.
        """

    @abstractmethod
    def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an existing order.

        Args:
            order_id: ID of the order to cancel.

        Returns:
            True if cancellation successful.
        """

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """
        Get all current open positions.

        Returns:
            List of Position objects.
        """

    @abstractmethod
    def get_account_value(self) -> float:
        """
        Get total account value in USD.

        Returns:
            Account value in USD.
        """

    @property
    def is_connected(self) -> bool:
        """Return whether the broker is currently connected."""
        return self._is_connected

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"host={self.host}, port={self.port}, "
            f"connected={self._is_connected})"
        )
