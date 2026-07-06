"""Tests for evaluation metrics aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Iterable

import pytest

from quant_signal_system.contracts.evaluation import SignalEvaluation
from quant_signal_system.contracts.signals import (
    Direction,
    ExecutionStatus,
    ExposureEffect,
    SignalAction,
    SignalEvent,
)
from quant_signal_system.evaluation.metrics import (
    aggregate_signal_metrics,
    compute_portfolio_metrics,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _feature_snapshot() -> object:
    from quant_signal_system.contracts.features import FeatureSnapshot

    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap-1",
        symbol="300346",
        market_data_time=_utc("2025-06-02T09:31:00+00:00"),
        generated_at=_utc("2025-06-02T09:31:00+00:00"),
        feature_version="f1",
        lookback_window="3bars",
        features={"close": 42.0},
        missing_data_flags=(),
        input_bar_range="2025-06-02T09:29:00..2025-06-02T09:31:00",
    )


def _signal(signal_id: str, direction: Direction, symbol: str = "300346") -> SignalEvent:
    return SignalEvent(
        schema_version="signal-event-v1",
        signal_id=signal_id,
        symbol=symbol,
        direction=direction,
        signal_action=SignalAction.BUY if direction == Direction.BUY else SignalAction.RISK_AVOID,
        exposure_effect=ExposureEffect.INCREASE_LONG,
        event_time=_utc("2025-06-02T09:31:00+00:00"),
        market_data_time=_utc("2025-06-02T09:31:00+00:00"),
        ingest_time=_utc("2025-06-02T09:31:00+00:00"),
        executable_time=_utc("2025-06-02T09:32:00+00:00"),
        reference_price=Decimal("42.00"),
        executable_price=None,
        executable_price_source=None,
        execution_status=ExecutionStatus.UNKNOWN_AT_EVENT_TIME,
        unexecutable_reason=None,
        score=Decimal("0.7"),
        confidence=Decimal("0.6"),
        horizon_seconds=900,
        reason_codes=("TEST_REASON",),
        invalid_condition=None,
        feature_snapshot=_feature_snapshot(),
        market_regime=None,
        strategy_name="rule_vol_breakout",
        strategy_version="v1",
        feature_version="f1",
        code_version="cv1",
        parameter_hash="h",
        data_source_version="dv1",
        as_of_version="asof-v1",
        created_at=_utc("2025-06-02T09:31:00+00:00"),
    )


def _evaluation(signal_id: str, net_return: Decimal | None = Decimal("0.01"), mfe: Decimal | None = Decimal("0.02"), mae: Decimal | None = Decimal("0.005")) -> SimpleNamespace:
    return SimpleNamespace(
        signal_id=signal_id,
        net_return=net_return,
        direction_return=net_return,
        mfe=mfe,
        mae=mae,
        reason_codes=("TEST_REASON",),
    )


class TestAggregateSignalMetrics:
    def test_empty_signals(self) -> None:
        result = aggregate_signal_metrics([], {}, {})
        assert result == []

    def test_single_signal(self) -> None:
        signal = _signal("s1", Direction.BUY)
        ev = _evaluation("s1", net_return=Decimal("0.01"))
        result = aggregate_signal_metrics([signal], {"s1": ev}, {"s1": date(2025, 6, 2)})
        assert len(result) == 1
        metrics = result[0]
        assert metrics.strategy_name == "rule_vol_breakout"
        assert metrics.sample_count == 1
        assert metrics.win_count == 1
        assert metrics.avg_net_return == Decimal("0.01")

    def test_buckets_by_direction(self) -> None:
        s1 = _signal("s1", Direction.BUY)
        s2 = _signal("s2", Direction.SELL)
        ev1 = _evaluation("s1", net_return=Decimal("0.01"))
        ev2 = _evaluation("s2", net_return=Decimal("-0.01"))
        result = aggregate_signal_metrics(
            [s1, s2],
            {"s1": ev1, "s2": ev2},
            {"s1": date(2025, 6, 2), "s2": date(2025, 6, 2)},
        )
        assert len(result) == 2
        directions = {m.direction for m in result}
        assert directions == {1, -1}

    def test_unexecutable_does_not_count_as_win(self) -> None:
        s1 = _signal("s1", Direction.BUY)
        ev1 = _evaluation("s1", net_return=None)
        result = aggregate_signal_metrics([s1], {"s1": ev1}, {"s1": date(2025, 6, 2)})
        assert result[0].unexecutable_count == 1
        assert result[0].win_count == 0


class TestComputePortfolioMetrics:
    def test_no_daily_values(self) -> None:
        ledger = SimpleNamespace(initial_cash=Decimal("1000000"), cash=Decimal("1000000"), pending_settlement_count=lambda: 0)
        metrics = compute_portfolio_metrics(ledger, {})
        assert metrics.days == 0
        assert metrics.total_return == Decimal("0")

    def test_profit(self) -> None:
        ledger = SimpleNamespace(
            initial_cash=Decimal("1000000"),
            cash=Decimal("1100000"),
            pending_settlement_count=lambda: 0,
        )
        daily = {
            date(2025, 6, 1): Decimal("1000000"),
            date(2025, 6, 2): Decimal("950000"),
            date(2025, 6, 3): Decimal("1100000"),
        }
        metrics = compute_portfolio_metrics(ledger, daily)
        assert metrics.total_return == Decimal("0.1")
        assert metrics.days == 3
        assert metrics.max_drawdown > 0
