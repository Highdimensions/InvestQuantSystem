"""Portfolio ledger combining cash, position, and settlement."""

from __future__ import annotations

from datetime import timedelta
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from quant_signal_system.contracts.portfolio import OrderSide, PaperFill
from quant_signal_system.portfolio.cash import CashLedger
from quant_signal_system.portfolio.position import PositionLedger
from quant_signal_system.portfolio.policy import PortfolioPolicy
from quant_signal_system.portfolio.settlement import SettlementRecord


@dataclass
class PortfolioLedger:
    """A-share portfolio state with T+1 settlement.

    Cash, position, and settlement state are updated atomically.
    """

    initial_cash: Decimal
    portfolio_id: str
    paper_run_id: str
    policy: PortfolioPolicy = PortfolioPolicy()
    lot_size: int = 100

    _cash: CashLedger = field(init=False)
    _positions: PositionLedger = field(init=False)
    _settlement: list[SettlementRecord] = field(init=False, default_factory=list)
    _fills: dict[str, PaperFill] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self._cash = CashLedger(self.initial_cash)
        self._positions = PositionLedger()

    @property
    def cash(self) -> Decimal:
        return self._cash.cash

    def get_position(self, symbol: str) -> Decimal:
        return self._positions.get(symbol)

    def get_sellable_quantity(self, symbol: str, as_of: datetime) -> Decimal:
        position = self._positions.get(symbol)
        settled = self.settled_quantity(symbol, as_of)
        return min(settled, position)

    def settled_quantity(self, symbol: str, as_of: datetime) -> Decimal:
        total = Decimal("0")
        for r in self._settlement:
            if r.symbol == symbol and r.settle_date <= as_of:
                total += r.quantity
        return total

    def apply_fill(self, fill: PaperFill, side: OrderSide, symbol: str, as_of: datetime) -> None:
        if fill.paper_fill_id in self._fills:
            raise ValueError(f"duplicate fill {fill.paper_fill_id}")
        self._fills[fill.paper_fill_id] = fill

        quantity = fill.quantity

        if side == OrderSide.BUY:
            self._cash.debit(fill.fill_price * quantity)
            self._cash.credit(-fill.fee)
            self._positions.add(symbol, quantity)
            self._settlement.append(
                SettlementRecord(
                    symbol=symbol,
                    buy_date=as_of,
                    settle_date=as_of + timedelta(days=1),
                    quantity=quantity,
                )
            )
        else:
            self._cash.credit(fill.fill_price * quantity)
            self._cash.debit(fill.fee)
            self._positions.subtract(symbol, quantity)

    def total_value(self, prices: dict[str, Decimal]) -> Decimal:
        return self._cash.cash + self._positions.total_value(prices)

    def realized_pnl(self) -> Decimal:
        return self._cash.realized_pnl()

    def pending_settlement_count(self) -> int:
        return len(self._settlement)
