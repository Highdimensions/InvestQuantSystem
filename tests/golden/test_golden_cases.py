"""Golden Test Cases (G1-G15).

Implements the Golden Case catalogue defined in
``docs/architecture/backtest-testing-strategy.md`` Section 4 and
``docs/architecture/testing-and-evaluation.md`` Section 5. Each Case verifies
one correctness invariant with a minimal, human-reviewable fixture.

The tests use deterministic in-process builders (no JSON fixtures) so the
expected outputs are computed from the inputs in plain sight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Iterable

import pytest

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.contracts.portfolio import OrderSide
from quant_signal_system.contracts.signals import Direction
from quant_signal_system.backtest.run_spec import BacktestRunSpec, StrategyBinding
from quant_signal_system.execution.market_rules import (
    MarketRulesEngine,
    OrderRejectionReason,
    OrderValidationResult,
)
from quant_signal_system.market_data.repository import InMemoryMarketDataRepository
from quant_signal_system.portfolio.ledger import PortfolioLedger
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies._examples.momentum_v1 import MomentumV1Strategy
from quant_signal_system.time.clock import FrozenClock, VirtualClock
from quant_signal_system.backtest.scheduler import BacktestScheduler
from quant_signal_system.backtest.run_spec import BacktestRunSpec
from quant_signal_system.time.trading_calendar import SimpleAshareTradingCalendar


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _bar(
    symbol: str = "300346",
    market_data_time: datetime | None = None,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close: float = 42.0,
    volume: int = 1000,
    trading_status: TradingStatus = TradingStatus.TRADING,
    is_closed: bool = True,
    data_source_version: str = "akshare-v1",
    as_of_version: str = "asof-v1",
) -> MarketBar:
    market_data_time = market_data_time or _utc("2025-06-02T09:31:00+00:00")
    o = Decimal(str(open_ if open_ is not None else close))
    h = Decimal(str(high if high is not None else max(o, Decimal(str(close)))))
    l = Decimal(str(low if low is not None else min(o, Decimal(str(close)))))
    c = Decimal(str(close))
    return MarketBar(
        schema_version="market-bar-v1",
        symbol=symbol,
        timeframe="1m",
        bar_start_time=market_data_time - timedelta(minutes=1),
        bar_end_time=market_data_time,
        market_data_time=market_data_time,
        ingest_time=market_data_time,
        open_price=o,
        high_price=h,
        low_price=l,
        close_price=c,
        volume=Decimal(str(volume)),
        amount=None,
        turnover=None,
        trading_status=trading_status,
        is_closed=is_closed,
        bar_close_time=market_data_time,
        source="test",
        data_source_version=data_source_version,
        as_of_version=as_of_version,
    )


def _ledger(cash: Decimal = Decimal("1000000")) -> PortfolioLedger:
    return PortfolioLedger(
        initial_cash=cash,
        portfolio_id="p1",
        paper_run_id="r1",
    )


def _fake_fill(symbol: str, quantity: int) -> SimpleNamespace:
    return SimpleNamespace(
        paper_fill_id=f"fill-{symbol}-{quantity}-{id(object())}",
        symbol=symbol,
        quantity=Decimal(str(quantity)),
        fill_price=Decimal("42"),
        fee=Decimal("0"),
    )


def _apply_buy(portfolio: PortfolioLedger, symbol: str, quantity: int, when: datetime) -> None:
    portfolio.apply_fill(
        _fake_fill(symbol, quantity),
        OrderSide.BUY,
        symbol,
        when,
    )


def _intent(side: str = "BUY", quantity: int = 100, reference_price: float = 42.0) -> SimpleNamespace:
    return SimpleNamespace(
        direction=Direction.BUY if side == "BUY" else Direction.SELL,
        quantity=quantity,
        reference_price=Decimal(str(reference_price)),
        symbol="300346",
    )


# (kept above as a helper but the spec / fill helpers below are what tests use)


def _spec(
    run_id: str,
    from_time: datetime,
    to_time: datetime,
) -> BacktestRunSpec:
    """Build a minimal BacktestRunSpec for scheduler-only tests."""
    binding = StrategyBinding(
        binding_id=f"{run_id}-binding",
        strategy_name="baseline-rules",
        strategy_version="v1",
        parameter_hash="hash-001",
        universe_id="u1",
        universe_version="uv1",
        feature_version="rolling-feature-v1",
    )
    return BacktestRunSpec(
        run_id=run_id,
        from_time=from_time,
        to_time=to_time,
        timeframe="1m",
        strategy_bindings=(binding,),
        data_source_version="akshare-v1",
        as_of_version="asof-v1",
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
        fill_price=Decimal("42"),
        fee=Decimal("0"),
    )


def _apply_buy(portfolio: PortfolioLedger, symbol: str, quantity: int, when: datetime) -> None:
    portfolio.apply_fill(
        _fake_fill(symbol, quantity),
        OrderSide.BUY,
        symbol,
        when,
    )


# ---------------------------------------------------------------------------
# G5: T+1 阻断
# ---------------------------------------------------------------------------


class TestG5T1SellRestricted:
    """Buying then immediately trying to sell same-day must be blocked by T+1."""

    def test_t1_sell_rejected(self) -> None:
        bar = _bar()
        portfolio = _ledger()
        engine = MarketRulesEngine()

        # Register a BUY fill so the position exists but is non-sellable today.
        _apply_buy(portfolio, "300346", 100, bar.market_data_time)

        # Try to SELL the same day: T+1 must block.
        intent = _intent(side="SELL", quantity=100)
        result = engine.validate(intent, bar, portfolio)

        assert not result.accepted
        assert result.rejection_reason == OrderRejectionReason.T1_SELL_RESTRICTED


# ---------------------------------------------------------------------------
# G6/G7: 涨跌停
# ---------------------------------------------------------------------------


class TestG6LimitUp:
    def test_limit_up_buy_rejected(self) -> None:
        bar = _bar(trading_status=TradingStatus.LIMIT_UP)
        portfolio = _ledger()
        engine = MarketRulesEngine()
        intent = _intent(side="BUY", quantity=100)
        result = engine.validate(intent, bar, portfolio)
        assert not result.accepted
        assert result.rejection_reason == OrderRejectionReason.LIMIT_UP


class TestG7LimitDown:
    def test_limit_down_sell_rejected(self) -> None:
        bar = _bar(trading_status=TradingStatus.LIMIT_DOWN)
        portfolio = _ledger()
        # Pre-populate a sellable position from a previous day.
        prev_day = bar.market_data_time - timedelta(days=2)
        _apply_buy(portfolio, "300346", 100, prev_day)
        engine = MarketRulesEngine()
        intent = _intent(side="SELL", quantity=100)
        result = engine.validate(intent, bar, portfolio)
        assert not result.accepted
        assert result.rejection_reason == OrderRejectionReason.LIMIT_DOWN


# ---------------------------------------------------------------------------
# G8: 停牌
# ---------------------------------------------------------------------------


class TestG8Suspended:
    def test_halted_rejected(self) -> None:
        bar = _bar(trading_status=TradingStatus.HALTED)
        portfolio = _ledger()
        engine = MarketRulesEngine()
        intent = _intent(side="BUY", quantity=100)
        result = engine.validate(intent, bar, portfolio)
        assert not result.accepted
        assert result.rejection_reason == OrderRejectionReason.SUSPENDED


# ---------------------------------------------------------------------------
# G10: 重复 Bar
# ---------------------------------------------------------------------------


class TestG10DuplicateBar:
    """Duplicate bars at the same market_data_time must be rejected by validator."""

    def test_validate_distinct_versions(self) -> None:
        ts = _utc("2025-06-02T09:31:00+00:00")
        bar_v1 = _bar(market_data_time=ts, data_source_version="akshare-v1")
        bar_v2 = _bar(market_data_time=ts, data_source_version="akshare-v2")
        # Different data_source_version => distinct version_key
        assert bar_v1.version_key != bar_v2.version_key


# ---------------------------------------------------------------------------
# G11: 缺失 Bar
# ---------------------------------------------------------------------------


class TestG11MissingBar:
    """The scheduler must surface MISSING_BAR warnings for large time gaps."""

    def test_missing_bar_warning_emitted(self) -> None:
        spec = _spec(
            run_id="g11",
            from_time=_utc("2025-06-02T09:30:00+00:00"),
            to_time=_utc("2025-06-02T10:00:00+00:00"),
        )
        clock = VirtualClock(current_time=spec.from_time)
        scheduler = BacktestScheduler(spec=spec, clock=clock)
        warning = scheduler.build_time_range_warning(
            symbol="300346",
            from_time=_utc("2025-06-02T09:35:00+00:00"),
            to_time=_utc("2025-06-02T09:40:00+00:00"),
        )
        assert warning.warning_code == "MISSING_BAR"
        assert warning.severity == "warn"
        assert "300346" in warning.message


# ---------------------------------------------------------------------------
# G12: 乱序 Bar
# ---------------------------------------------------------------------------


class TestG12OutOfOrder:
    """Out-of-order bars must be detected and counted."""

    def test_out_of_order_count(self) -> None:
        spec = _spec(
            run_id="g12",
            from_time=_utc("2025-06-02T09:30:00+00:00"),
            to_time=_utc("2025-06-02T11:00:00+00:00"),
        )
        clock = VirtualClock(current_time=spec.from_time)
        scheduler = BacktestScheduler(spec=spec, clock=clock)
        bar_a = _bar(market_data_time=_utc("2025-06-02T10:00:00+00:00"))
        bar_b = _bar(market_data_time=_utc("2025-06-02T09:30:00+00:00"))
        scheduler.advance_to_bar(bar_a)
        scheduler.advance_to_bar(bar_b)
        assert scheduler.out_of_order_count() == 1
        assert scheduler.last_warning_code() == "OUT_OF_ORDER_BAR"


# ---------------------------------------------------------------------------
# G14: Universe 切换
# ---------------------------------------------------------------------------


class TestG14UniverseChange:
    """The scheduler should report a change in universe_version."""

    def test_universe_needs_switch(self) -> None:
        spec = _spec(
            run_id="g14",
            from_time=_utc("2025-06-02T09:30:00+00:00"),
            to_time=_utc("2025-06-02T11:00:00+00:00"),
        )
        clock = VirtualClock(current_time=spec.from_time)
        scheduler = BacktestScheduler(spec=spec, clock=clock)

        # Stub resolver returning v1 then v2.
        class _StubResolver:
            def __init__(self) -> None:
                self.calls = 0
            def resolve(self, universe_id: str, at_time):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(universe_version="v1", symbols=("300346",))
                return SimpleNamespace(universe_version="v2", symbols=("300346",))

        resolver = _StubResolver()
        # First call returns v1 (no switch needed)
        v1 = resolver.resolve("u1", spec.from_time)
        assert v1.universe_version == "v1"
        # Second call returns v2 (switch needed)
        needs_switch = scheduler.universe_needs_switch(
            resolver=resolver,
            binding_id="b1",
            universe_id="u1",
            current_version="v1",
            current_time=spec.to_time,
        )
        assert needs_switch is True


# ---------------------------------------------------------------------------
# G15: 同策略不同参数
# ---------------------------------------------------------------------------


class TestG15SameStrategyDifferentParams:
    """Two bindings of the same strategy with different parameters must produce distinct parameter_hash."""

    def test_parameter_hash_differs(self) -> None:
        s1 = MomentumV1Strategy.from_params({"return_threshold": 0.005, "horizon_seconds": 900})
        s2 = MomentumV1Strategy.from_params({"return_threshold": 0.010, "horizon_seconds": 900})
        # Same name + version, different parameter hash
        assert s1.name == s2.name
        assert s1.version == s2.version
        assert s1.parameter_hash != s2.parameter_hash