"""Tests for the A-share realistic cost model."""

from __future__ import annotations

from decimal import Decimal

import pytest

from quant_signal_system.contracts.signals import Direction
from quant_signal_system.evaluation.acshare_cost_model import ACShareCostModel


class TestACShareCostModel:
    def test_default_buy_rate(self) -> None:
        model = ACShareCostModel()
        # Buy: 3 bps commission + 1 bp transfer = 4 bps = 0.04 %
        rate = model.cost_rate(Direction.BUY)
        assert rate == Decimal("0.0004")

    def test_default_sell_rate_includes_stamp_duty(self) -> None:
        model = ACShareCostModel()
        # Sell: 3 bps commission + 5 bps stamp duty + 1 bp transfer = 9 bps
        rate = model.cost_rate(Direction.SELL)
        assert rate == Decimal("0.0009")

    def test_buy_higher_than_no_stamp_duty(self) -> None:
        model = ACShareCostModel()
        assert model.cost_rate(Direction.SELL) > model.cost_rate(Direction.BUY)

    def test_total_bps_buy(self) -> None:
        model = ACShareCostModel()
        assert model.total_bps(Direction.BUY) == Decimal("4")

    def test_total_bps_sell(self) -> None:
        model = ACShareCostModel()
        assert model.total_bps(Direction.SELL) == Decimal("9")

    def test_hold_returns_zero(self) -> None:
        model = ACShareCostModel()
        assert model.cost_rate(Direction.HOLD) == Decimal("0")

    def test_custom_commission(self) -> None:
        model = ACShareCostModel(buy_commission_bps=Decimal("2"))
        # Buy: 2 + 1 = 3 bps
        assert model.cost_rate(Direction.BUY) == Decimal("0.0003")

    def test_custom_stamp_duty(self) -> None:
        model = ACShareCostModel(sell_stamp_duty_bps=Decimal("10"))
        # Sell: 3 + 10 + 1 = 14 bps
        assert model.cost_rate(Direction.SELL) == Decimal("0.0014")

    def test_min_commission_field_exists(self) -> None:
        model = ACShareCostModel(min_commission_yuan=Decimal("5"))
        assert model.min_commission_yuan == Decimal("5")

    def test_version(self) -> None:
        model = ACShareCostModel()
        assert model.cost_model_version == "ac-share-cost-v1"