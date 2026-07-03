"""Cost model interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_signal_system.contracts.signals import Direction


@dataclass(frozen=True, slots=True)
class FixedBpsCostModel:
    cost_model_version: str = "fixed-bps-cost-v1"
    buy_bps: Decimal = Decimal("5")
    sell_bps: Decimal = Decimal("15")

    def cost_rate(self, direction: Direction) -> Decimal:
        if direction == Direction.BUY:
            return self.buy_bps / Decimal("10000")
        if direction == Direction.SELL:
            return self.sell_bps / Decimal("10000")
        return Decimal("0")

