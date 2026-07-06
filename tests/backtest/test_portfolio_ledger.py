"""Tests for PortfolioLedger."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.portfolio import OrderSide, PaperFill
from quant_signal_system.portfolio.ledger import PortfolioLedger


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _ledger(cash: Decimal = Decimal("1000000")) -> PortfolioLedger:
    return PortfolioLedger(
        initial_cash=cash,
        portfolio_id="p1",
        paper_run_id="r1",
    )


def _fill(fill_id: str = "fill-1") -> PaperFill:
    return PaperFill(
        paper_fill_id=fill_id,
        paper_run_id="r1",
        paper_order_id=f"order-{fill_id}",
        signal_id="sig-1",
        cost_model_version="cmv1",
        fill_model_version="fmv1",
        fill_time=_utc("2025-06-02T09:31:00+00:00"),
        fill_price=Decimal("42.00"),
        quantity=Decimal("100"),
        fee=Decimal("0.50"),
        tax=Decimal("0"),
        slippage=Decimal("0"),
    )


class TestPortfolioLedger:
    def test_initial_cash(self) -> None:
        ledger = _ledger(cash=Decimal("1000000"))
        assert ledger.cash == Decimal("1000000")

    def test_buy_reduces_cash_and_increases_position(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("fill-buy"), OrderSide.BUY, "300346", _utc("2025-06-02T09:31:00+00:00"))
        assert ledger.cash == Decimal("995799.5")
        assert ledger.get_position("300346") == Decimal("100")

    def test_sell_increases_cash_and_decreases_position(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("fill-buy"), OrderSide.BUY, "300346", _utc("2025-06-01T09:31:00+00:00"))
        ledger.apply_fill(_fill("fill-sell"), OrderSide.SELL, "300346", _utc("2025-06-02T09:31:00+00:00"))
        assert ledger.get_position("300346") == Decimal("0")
        assert ledger.cash == Decimal("999999.00")

    def test_duplicate_fill_raises(self) -> None:
        ledger = _ledger()
        fill = _fill("fill-dup")
        ledger.apply_fill(fill, OrderSide.BUY, "300346", _utc("2025-06-02T09:31:00+00:00"))
        with pytest.raises(ValueError, match="duplicate fill"):
            ledger.apply_fill(fill, OrderSide.BUY, "300346", _utc("2025-06-02T09:31:00+00:00"))

    def test_sell_without_position_raises(self) -> None:
        ledger = _ledger()
        with pytest.raises(ValueError):
            ledger.apply_fill(_fill("fill-solo"), OrderSide.SELL, "300346", _utc("2025-06-02T09:31:00+00:00"))

    def test_cash_conservation(self) -> None:
        buy_price = Decimal("10.0")
        sell_price = Decimal("11.0")
        buy_fill = PaperFill(
            paper_fill_id="fill-c1",
            paper_run_id="r1",
            paper_order_id="order-c1",
            signal_id="sig-1",
            cost_model_version="cmv1",
            fill_model_version="fmv1",
            fill_time=_utc("2025-06-01T09:31:00+00:00"),
            fill_price=buy_price,
            quantity=Decimal("100"),
            fee=Decimal("0.50"),
            tax=Decimal("0"),
            slippage=Decimal("0"),
        )
        sell_fill = PaperFill(
            paper_fill_id="fill-c2",
            paper_run_id="r1",
            paper_order_id="order-c2",
            signal_id="sig-1",
            cost_model_version="cmv1",
            fill_model_version="fmv1",
            fill_time=_utc("2025-06-02T09:31:00+00:00"),
            fill_price=sell_price,
            quantity=Decimal("100"),
            fee=Decimal("0.50"),
            tax=Decimal("0"),
            slippage=Decimal("0"),
        )
        ledger = _ledger()
        ledger.apply_fill(buy_fill, OrderSide.BUY, "300346", _utc("2025-06-01T09:31:00+00:00"))
        ledger.apply_fill(sell_fill, OrderSide.SELL, "300346", _utc("2025-06-02T09:31:00+00:00"))
        expected = Decimal("1000000") - buy_price * Decimal("100") - Decimal("0.50") + sell_price * Decimal("100") - Decimal("0.50")
        assert ledger.cash == expected

    def test_total_value(self) -> None:
        ledger = _ledger()
        ledger.apply_fill(_fill("fill-t1"), OrderSide.BUY, "300346", _utc("2025-06-02T09:31:00+00:00"))
        prices = {"300346": Decimal("42.00")}
        assert ledger.total_value(prices) == ledger.cash + Decimal("4200.0")
