"""Portfolio settlement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class SettlementRecord:
    symbol: str
    buy_date: datetime
    settle_date: datetime
    quantity: Decimal


class Settlement:
    """Tracks T+1 settlement for sell eligibility."""

    def __init__(self) -> None:
        self._pending: list[SettlementRecord] = []

    def add(self, record: SettlementRecord) -> None:
        self._pending.append(record)

    def settle(self, as_of: datetime) -> None:
        self._pending = [r for r in self._pending if r.settle_date > as_of]

    def sellable_quantity(self, symbol: str, as_of: datetime) -> Decimal:
        return sum(
            r.quantity for r in self._pending
            if r.symbol == symbol and r.settle_date <= as_of
        )

    def pending_count(self) -> int:
        return len(self._pending)
