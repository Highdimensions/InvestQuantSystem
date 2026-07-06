"""OrderIntent: immutable bridge from SignalEvent to execution intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from quant_signal_system.contracts.signals import (
    Direction,
    ExecutionStatus,
    SignalAction,
    SignalEvent,
)


def _order_intent_id(signal_id: str) -> str:
    import hashlib
    return hashlib.sha256(f"intent|{signal_id}".encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class OrderIntent:
    schema_version: str = "order-intent-v1"
    intent_id: str = ""
    signal_id: str = ""
    binding_id: str = ""
    symbol: str = ""
    direction: Direction = Direction.HOLD
    action: SignalAction = SignalAction.HOLD
    quantity: int = 0
    reference_price: Decimal = field(default_factory=lambda: Decimal("0"))
    target_price: Decimal | None = None
    execution_status: ExecutionStatus = ExecutionStatus.UNKNOWN_AT_EVENT_TIME
    created_at: datetime = field(default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc))

    def __post_init__(self) -> None:
        if not self.intent_id:
            raise ValueError("intent_id is required")
        if not self.signal_id:
            raise ValueError("signal_id is required")
        if self.quantity < 0:
            raise ValueError("quantity must be non-negative")

    @classmethod
    def from_signal(
        cls,
        signal: SignalEvent,
        *,
        binding_id: str = "",
        quantity: int = 100,
    ) -> OrderIntent:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        direction = signal.direction
        action = signal.signal_action
        qty = quantity if direction == Direction.BUY else 0
        if action in (SignalAction.REDUCE_LONG, SignalAction.CLEAR_LONG):
            qty = quantity
        return cls(
            intent_id=_order_intent_id(signal.signal_id),
            signal_id=signal.signal_id,
            binding_id=binding_id,
            symbol=signal.symbol,
            direction=direction,
            action=action,
            quantity=qty,
            reference_price=signal.reference_price,
            target_price=None,
            execution_status=signal.execution_status,
            created_at=datetime.now(timezone.utc),
        )
