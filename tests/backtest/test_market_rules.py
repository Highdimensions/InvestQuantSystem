"""Tests for MarketRulesEngine."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.contracts.portfolio import OrderSide
from quant_signal_system.contracts.signals import Direction
from quant_signal_system.execution.market_rules import (
    MarketRulesEngine,
    OrderRejectionReason,
    OrderValidationResult,
)
from quant_signal_system.portfolio.ledger import PortfolioLedger


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _bar(
    symbol: str = "300346",
    market_data_time: datetime | None = None,
    close: float = 42.0,
    volume: int = 1000,
    trading_status: TradingStatus = TradingStatus.TRADING,
) -> MarketBar:
    market_data_time = market_data_time or _utc("2025-06-02T09:31:00+00:00")
    close_dec = Decimal(str(close))
    return MarketBar(
        schema_version="market-bar-v1",
        symbol=symbol,
        timeframe="1m",
        bar_start_time=market_data_time,
        bar_end_time=market_data_time,
        market_data_time=market_data_time,
        ingest_time=market_data_time,
        open_price=close_dec,
        high_price=close_dec,
        low_price=close_dec,
        close_price=close_dec,
        volume=Decimal(str(volume)),
        amount=None,
        turnover=None,
        trading_status=trading_status,
        is_closed=True,
        bar_close_time=market_data_time,
        source="test",
        data_source_version="test-v1",
        as_of_version="asof-v1",
    )


def _intent(side: str = "BUY", quantity: int = 100) -> SimpleNamespace:
    return SimpleNamespace(
        direction=Direction.BUY if side == "BUY" else Direction.SELL,
        quantity=quantity,
        reference_price=Decimal("42.00"),
        symbol="300346",
    )


def _ledger(cash: Decimal = Decimal("1000000")) -> PortfolioLedger:
    return PortfolioLedger(
        initial_cash=cash,
        portfolio_id="p1",
        paper_run_id="r1",
    )


def _fake_fill(symbol: str, quantity: int) -> SimpleNamespace:
    return SimpleNamespace(
        paper_fill_id=f"fill-{symbol}-{quantity}",
        symbol=symbol,
        quantity=Decimal(str(quantity)),
        fill_price=Decimal("42.00"),
        fee=Decimal("0"),
    )


class TestMarketRulesEngine:
    def test_normal_buy_accepted(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar()
        ledger = _ledger()
        result = engine.validate(_intent("BUY"), bar, ledger)
        assert result.accepted is True

    def test_normal_sell_accepted(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar(market_data_time=_utc("2025-06-03T09:31:00+00:00"))
        ledger = _ledger()
        ledger.apply_fill(
            _fake_fill("300346", 100),
            OrderSide.BUY,
            "300346",
            _utc("2025-06-01T09:31:00+00:00"),
        )
        intent = _intent("SELL")
        result = engine.validate(intent, bar, ledger)
        assert result.accepted is True

    def test_limit_up_buy_rejected(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar(trading_status=TradingStatus.LIMIT_UP)
        ledger = _ledger()
        result = engine.validate(_intent("BUY"), bar, ledger)
        assert result.accepted is False
        assert result.rejection_reason == OrderRejectionReason.LIMIT_UP

    def test_limit_down_sell_rejected(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar(trading_status=TradingStatus.LIMIT_DOWN)
        ledger = _ledger()
        result = engine.validate(_intent("SELL"), bar, ledger)
        assert result.accepted is False
        assert result.rejection_reason == OrderRejectionReason.LIMIT_DOWN

    def test_halted_rejected(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar(trading_status=TradingStatus.HALTED)
        ledger = _ledger()
        result = engine.validate(_intent("BUY"), bar, ledger)
        assert result.accepted is False
        assert result.rejection_reason == OrderRejectionReason.SUSPENDED

    def test_lot_size_violation_rejected(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar()
        ledger = _ledger()
        intent = _intent("BUY", quantity=50)
        result = engine.validate(intent, bar, ledger)
        assert result.accepted is False
        assert result.rejection_reason == OrderRejectionReason.LOT_SIZE_VIOLATION

    def test_t1_sell_rejected(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar(market_data_time=_utc("2025-06-02T09:31:00+00:00"))
        ledger = _ledger()
        ledger.apply_fill(
            _fake_fill("300346", 100),
            OrderSide.BUY,
            "300346",
            _utc("2025-06-02T09:31:00+00:00"),
        )
        intent = _intent("SELL")
        result = engine.validate(intent, bar, ledger)
        assert result.accepted is False
        assert result.rejection_reason == OrderRejectionReason.T1_SELL_RESTRICTED

    def test_insufficient_cash_rejected(self) -> None:
        engine = MarketRulesEngine()
        bar = _bar()
        ledger = _ledger(cash=Decimal("0"))
        result = engine.validate(_intent("BUY"), bar, ledger)
        assert result.accepted is False
        assert result.rejection_reason == OrderRejectionReason.INSUFFICIENT_CASH
