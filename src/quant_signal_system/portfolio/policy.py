"""Portfolio policy constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PortfolioPolicy:
    max_single_position_ratio: Decimal = Decimal("0.1")
    max_total_position_ratio: Decimal = Decimal("0.95")
    min_cash_ratio: Decimal = Decimal("0.05")
    max_turnover_per_bar: Decimal = Decimal("1.0")
