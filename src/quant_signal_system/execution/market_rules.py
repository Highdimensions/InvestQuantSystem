"""A-share market rules engine.

Validates ``OrderIntent`` against A-share trading rules.  All validation is
deterministic: the same inputs always produce the same result.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.contracts.signals import Direction


class OrderRejectionReason(StrEnum):
    """Why an order was rejected by the market rules engine."""

    T1_SELL_RESTRICTED = "T1_SELL_RESTRICTED"
    LIMIT_UP = "LIMIT_UP"
    LIMIT_DOWN = "LIMIT_DOWN"
    SUSPENDED = "SUSPENDED"
    INSUFFICIENT_VOLUME = "INSUFFICIENT_VOLUME"
    LOT_SIZE_VIOLATION = "LOT_SIZE_VIOLATION"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_POSITION = "INSUFFICIENT_POSITION"


@dataclass(frozen=True, slots=True)
class OrderValidationResult:
    """Outcome of validating an order intent."""

    accepted: bool
    rejection_reason: OrderRejectionReason | None = None
    rejection_detail: str = ""

    def __post_init__(self) -> None:
        if not self.accepted and self.rejection_reason is None:
            raise ValueError("rejected result must have a rejection_reason")


class MarketRulesEngine:
    """Validates ``OrderIntent`` instances against A-share market rules.

    The engine checks:
    - Lot size (default 100 shares)
    - Trading status (halted / limit up / limit down)
    - Available bar volume
    - Sufficient cash for buys (delegated to portfolio)
    - T+1 sell restrictions (delegated to portfolio)
    - Sufficient position for sells (delegated to portfolio)
    """

    def __init__(
        self,
        lot_size: int = 100,
        min_volume_ratio: float = 0.01,
    ) -> None:
        self.lot_size = lot_size
        self.min_volume_ratio = min_volume_ratio

    def validate(
        self,
        intent,
        bar: MarketBar,
        portfolio,
    ) -> OrderValidationResult:
        """Validate an ``OrderIntent`` against market and portfolio rules.

        Parameters
        ----------
        intent:
            The order intent to validate. Must have:
            - ``direction`` (Direction)
            - ``quantity`` (int)
            - ``reference_price`` (Decimal)
            - ``symbol`` (str, optional for T+1 checks)
        bar:
            The triggering ``MarketBar``.
        portfolio:
            The ``PortfolioLedger`` whose state is used for cash/position checks.
        """
        quantity = Decimal(intent.quantity)

        if quantity <= 0:
            return OrderValidationResult(
                accepted=False,
                rejection_reason=OrderRejectionReason.LOT_SIZE_VIOLATION,
                rejection_detail="quantity must be positive",
            )

        if quantity % Decimal(self.lot_size) != 0:
            return OrderValidationResult(
                accepted=False,
                rejection_reason=OrderRejectionReason.LOT_SIZE_VIOLATION,
                rejection_detail=(
                    f"quantity {int(quantity)} is not a multiple of {self.lot_size}"
                ),
            )

        if bar.trading_status in (
            TradingStatus.HALTED,
            TradingStatus.UNKNOWN,
        ):
            return OrderValidationResult(
                accepted=False,
                rejection_reason=OrderRejectionReason.SUSPENDED,
                rejection_detail=f"trading status is {bar.trading_status.value}",
            )

        if bar.trading_status == TradingStatus.LIMIT_UP:
            if intent.direction == Direction.BUY:
                return OrderValidationResult(
                    accepted=False,
                    rejection_reason=OrderRejectionReason.LIMIT_UP,
                    rejection_detail="cannot buy at limit up",
                )

        if bar.trading_status == TradingStatus.LIMIT_DOWN:
            if intent.direction == Direction.SELL:
                return OrderValidationResult(
                    accepted=False,
                    rejection_reason=OrderRejectionReason.LIMIT_DOWN,
                    rejection_detail="cannot sell at limit down",
                )

        if bar.volume is not None and bar.volume > 0:
            if quantity > bar.volume:
                return OrderValidationResult(
                    accepted=False,
                    rejection_reason=OrderRejectionReason.INSUFFICIENT_VOLUME,
                    rejection_detail=(
                        f"order qty {int(quantity)} exceeds bar volume {int(bar.volume)}"
                    ),
                )

        if intent.direction == Direction.BUY:
            required_cash = intent.reference_price * quantity
            if portfolio.cash < required_cash:
                return OrderValidationResult(
                    accepted=False,
                    rejection_reason=OrderRejectionReason.INSUFFICIENT_CASH,
                    rejection_detail=(
                        f"required cash {required_cash}, available {portfolio.cash}"
                    ),
                )

        if intent.direction == Direction.SELL:
            symbol = getattr(intent, "symbol", "")
            sellable = portfolio.get_sellable_quantity(symbol, bar.market_data_time)
            if quantity > sellable:
                return OrderValidationResult(
                    accepted=False,
                    rejection_reason=OrderRejectionReason.T1_SELL_RESTRICTED,
                    rejection_detail=(
                        f"requested {int(quantity)}, sellable {int(sellable)} "
                        f"for {symbol}"
                    ),
                )
            position = portfolio.get_position(symbol)
            if quantity > position:
                return OrderValidationResult(
                    accepted=False,
                    rejection_reason=OrderRejectionReason.INSUFFICIENT_POSITION,
                    rejection_detail=(
                        f"requested {int(quantity)}, position {int(position)} "
                        f"for {symbol}"
                    ),
                )

        return OrderValidationResult(accepted=True)
