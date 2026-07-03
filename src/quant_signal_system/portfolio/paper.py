"""Simple A-share paper portfolio that never opens short positions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from quant_signal_system.contracts.portfolio import (
    OrderSide,
    PaperFill,
    PaperOrder,
    PaperOrderStatus,
    PaperPosition,
)
from quant_signal_system.contracts.signals import SignalAction, SignalEvent
from quant_signal_system.evaluation.cost_model import FixedBpsCostModel


@dataclass(slots=True)
class PaperPortfolio:
    portfolio_id: str
    paper_run_id: str
    cost_model: FixedBpsCostModel = FixedBpsCostModel()
    default_quantity: Decimal = Decimal("100")
    _positions: dict[str, Decimal] = field(default_factory=dict)
    _fills: dict[str, PaperFill] = field(default_factory=dict)

    def apply_signal(self, signal: SignalEvent, fill_price: Decimal) -> list[PaperOrder | PaperFill]:
        if signal.signal_action == SignalAction.HOLD:
            return []
        current_qty = self._positions.get(signal.symbol, Decimal("0"))
        if signal.signal_action == SignalAction.BUY:
            side = OrderSide.BUY
            qty = self.default_quantity
        else:
            side = OrderSide.SELL
            qty = min(current_qty, self.default_quantity)
            if qty <= 0:
                return []

        order_id = self._id("order", signal.signal_id)
        fill_id = self._id("fill", signal.signal_id)
        if fill_id in self._fills:
            return []

        now = signal.executable_time
        order = PaperOrder(
            paper_order_id=order_id,
            paper_run_id=self.paper_run_id,
            signal_id=signal.signal_id,
            strategy_version=signal.strategy_version,
            cost_model_version=self.cost_model.cost_model_version,
            fill_model_version="manual-fill-v1",
            symbol=signal.symbol,
            side=side,
            quantity=qty,
            order_time=now,
            assumed_order_type="MARKET_NEXT_AVAILABLE",
            status=PaperOrderStatus.FILLED,
        )
        rate = self.cost_model.cost_rate(signal.direction)
        fill = PaperFill(
            paper_fill_id=fill_id,
            paper_run_id=self.paper_run_id,
            paper_order_id=order_id,
            signal_id=signal.signal_id,
            cost_model_version=self.cost_model.cost_model_version,
            fill_model_version="manual-fill-v1",
            fill_time=now,
            fill_price=fill_price,
            quantity=qty,
            fee=fill_price * qty * rate,
            tax=Decimal("0"),
            slippage=Decimal("0"),
        )
        if side == OrderSide.BUY:
            self._positions[signal.symbol] = current_qty + qty
        else:
            self._positions[signal.symbol] = current_qty - qty
        self._fills[fill_id] = fill
        return [order, fill]

    def position(self, symbol: str, price: Decimal) -> PaperPosition:
        quantity = self._positions.get(symbol, Decimal("0"))
        return PaperPosition(
            portfolio_id=self.portfolio_id,
            paper_run_id=self.paper_run_id,
            symbol=symbol,
            as_of_time=datetime.now(timezone.utc),
            strategy_version="mixed",
            cost_model_version=self.cost_model.cost_model_version,
            fill_model_version="manual-fill-v1",
            quantity=quantity,
            average_cost=Decimal("0"),
            market_value=quantity * price,
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
        )

    def _id(self, prefix: str, signal_id: str) -> str:
        return hashlib.sha256(f"{self.paper_run_id}|{prefix}|{signal_id}".encode("utf-8")).hexdigest()[:24]

