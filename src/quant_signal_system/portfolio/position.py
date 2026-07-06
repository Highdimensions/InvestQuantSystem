"""Position tracking for portfolio ledger."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class PositionLedger:
    """Tracks per-symbol position quantities."""

    _positions: dict[str, Decimal]

    def __init__(self) -> None:
        self._positions = {}

    def get(self, symbol: str) -> Decimal:
        return self._positions.get(symbol, Decimal("0"))

    def add(self, symbol: str, quantity: Decimal) -> None:
        self._positions[symbol] = self.get(symbol) + quantity
        if self._positions[symbol] == Decimal("0"):
            del self._positions[symbol]

    def subtract(self, symbol: str, quantity: Decimal) -> None:
        current = self.get(symbol)
        if current < quantity:
            raise ValueError(f"cannot subtract {quantity} from position {current} for {symbol}")
        self._positions[symbol] = current - quantity
        if self._positions[symbol] == Decimal("0"):
            del self._positions[symbol]

    def symbols(self) -> list[str]:
        return list(self._positions.keys())

    def total_value(self, prices: dict[str, Decimal]) -> Decimal:
        return sum(self.get(s) * prices.get(s, Decimal("0")) for s in self._positions)
