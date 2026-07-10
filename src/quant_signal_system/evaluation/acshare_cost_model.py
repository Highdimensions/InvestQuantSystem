"""A-share realistic cost model.

Implements the tax-and-fee schedule defined in
``docs/architecture/testing-and-evaluation.md`` Section 2 / 3.2:

- Broker commission (both sides)
- Stamp duty (sell side only, 0.05 % = 5 bps)
- Transfer fee (both sides)

All rates are expressed in basis points (1 bp = 0.01 %). Default values match
the 2024-2026 A-share retail schedule. Override individual fields to model
discounted brokerage or institutional accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_signal_system.contracts.signals import Direction


@dataclass(frozen=True, slots=True)
class ACShareCostModel:
    """Realistic A-share transaction cost model.

    Cost components (default values represent typical retail rates as of 2024):
    - Broker commission (both sides): 0.03 % (3 bps)
    - Stamp duty (SELL only): 0.05 % (5 bps)
    - Transfer fee (both sides): 0.001 % (0.1 bps)
    """

    cost_model_version: str = "ac-share-cost-v1"

    # Broker commission
    buy_commission_bps: Decimal = Decimal("3")
    sell_commission_bps: Decimal = Decimal("3")

    # Stamp duty (sell side only)
    sell_stamp_duty_bps: Decimal = Decimal("5")

    # Transfer fee
    buy_transfer_fee_bps: Decimal = Decimal("1")
    sell_transfer_fee_bps: Decimal = Decimal("1")

    # Minimum commission per trade (yuan). 0 disables the floor.
    min_commission_yuan: Decimal = Decimal("5")

    def cost_rate(self, direction: Direction) -> Decimal:
        """Return the all-in cost rate (decimal fraction) for a given side.

        Examples:
            BUY:  0.03 % + 0.001 % = 0.031 % = Decimal("0.00031")
            SELL: 0.03 % + 0.05 % + 0.001 % = 0.081 % = Decimal("0.00081")
        """
        if direction == Direction.BUY:
            return (
                self.buy_commission_bps + self.buy_transfer_fee_bps
            ) / Decimal("10000")
        if direction == Direction.SELL:
            return (
                self.sell_commission_bps
                + self.sell_stamp_duty_bps
                + self.sell_transfer_fee_bps
            ) / Decimal("10000")
        return Decimal("0")

    def total_bps(self, direction: Direction) -> Decimal:
        """Return the all-in cost in basis points (handy for reports)."""
        if direction == Direction.BUY:
            return self.buy_commission_bps + self.buy_transfer_fee_bps
        if direction == Direction.SELL:
            return (
                self.sell_commission_bps
                + self.sell_stamp_duty_bps
                + self.sell_transfer_fee_bps
            )
        return Decimal("0")