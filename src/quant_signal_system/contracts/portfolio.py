"""Paper portfolio contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrderStatus(StrEnum):
    CREATED = "CREATED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class PaperOrder:
    paper_order_id: str
    paper_run_id: str
    signal_id: str
    strategy_version: str
    cost_model_version: str
    fill_model_version: str
    symbol: str
    side: OrderSide
    quantity: Decimal
    order_time: datetime
    assumed_order_type: str
    status: PaperOrderStatus

    def validate(self) -> None:
        require_aware_utc(self.order_time, "order_time")
        if self.quantity < 0:
            raise MarketDataValidationError("order quantity cannot be negative")


@dataclass(frozen=True, slots=True)
class PaperFill:
    paper_fill_id: str
    paper_run_id: str
    paper_order_id: str
    signal_id: str
    cost_model_version: str
    fill_model_version: str
    fill_time: datetime
    fill_price: Decimal
    quantity: Decimal
    fee: Decimal
    tax: Decimal
    slippage: Decimal


@dataclass(frozen=True, slots=True)
class PaperPosition:
    portfolio_id: str
    paper_run_id: str
    symbol: str
    as_of_time: datetime
    strategy_version: str
    cost_model_version: str
    fill_model_version: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal

