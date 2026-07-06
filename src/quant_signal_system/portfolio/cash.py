"""Cash management for portfolio ledger."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class CashLedger:
    initial_cash: Decimal
    _cash: Decimal

    def __init__(self, initial_cash: Decimal) -> None:
        self.initial_cash = initial_cash
        self._cash = initial_cash

    @property
    def cash(self) -> Decimal:
        return self._cash

    def credit(self, amount: Decimal) -> None:
        self._cash += amount

    def debit(self, amount: Decimal) -> None:
        if self._cash < amount:
            raise ValueError(f"insufficient cash: {self._cash} < {amount}")
        self._cash -= amount

    def realized_pnl(self) -> Decimal:
        return self._cash - self.initial_cash
