"""Tests for OrderIntent creation and determinism."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.backtest.order_intent import OrderIntent
from quant_signal_system.contracts.signals import (
    Direction,
    ExecutionStatus,
    SignalAction,
    SignalEvent,
)
from quant_signal_system.contracts.features import FeatureSnapshot


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _signal(
    signal_id: str = "sig-001",
    direction: Direction = Direction.BUY,
    action: SignalAction = SignalAction.BUY,
) -> SignalEvent:
    return SignalEvent(
        schema_version="signal-event-v1",
        signal_id=signal_id,
        symbol="300346",
        direction=direction,
        signal_action=action,
        exposure_effect=SignalEvent.__dataclass_fields__["exposure_effect"].default,
        event_time=_utc("2025-06-02T09:31:00+00:00"),
        market_data_time=_utc("2025-06-02T09:31:00+00:00"),
        ingest_time=_utc("2025-06-02T09:31:00+00:00"),
        executable_time=_utc("2025-06-02T09:32:00+00:00"),
        reference_price=Decimal("42.00"),
        executable_price=None,
        executable_price_source=None,
        execution_status=ExecutionStatus.UNKNOWN_AT_EVENT_TIME,
        unexecutable_reason=None,
        score=Decimal("0.70"),
        confidence=Decimal("0.60"),
        horizon_seconds=900,
        reason_codes=("TEST_REASON",),
        invalid_condition=None,
        feature_snapshot=_snapshot(),
        market_regime=None,
        strategy_name="test",
        strategy_version="v1",
        feature_version="f1",
        code_version="cv1",
        parameter_hash="h",
        data_source_version="dv1",
        as_of_version="asof-v1",
        created_at=_utc("2025-06-02T09:31:00+00:00"),
    )


def _snapshot() -> FeatureSnapshot:
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


class TestOrderIntentFromSignal:
    def test_basic_buy(self) -> None:
        signal = _signal("sig-001", Direction.BUY, SignalAction.BUY)
        intent = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        assert intent.signal_id == "sig-001"
        assert intent.symbol == "300346"
        assert intent.direction == Direction.BUY
        assert intent.quantity == 100
        assert intent.reference_price == Decimal("42.00")
        assert intent.binding_id == "b1"

    def test_sell_sets_quantity_zero(self) -> None:
        signal = _signal("sig-001", Direction.SELL, SignalAction.RISK_AVOID)
        intent = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        assert intent.quantity == 0

    def test_reduce_long_keeps_quantity(self) -> None:
        signal = _signal("sig-001", Direction.SELL, SignalAction.REDUCE_LONG)
        intent = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        assert intent.quantity == 100

    def test_clear_long_keeps_quantity(self) -> None:
        signal = _signal("sig-001", Direction.SELL, SignalAction.CLEAR_LONG)
        intent = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        assert intent.quantity == 100

    def test_deterministic_intent_id(self) -> None:
        signal = _signal("sig-001")
        i1 = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        i2 = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        assert i1.intent_id == i2.intent_id

    def test_different_signal_produces_different_intent_id(self) -> None:
        sig1 = _signal("sig-001")
        sig2 = _signal("sig-002")
        i1 = OrderIntent.from_signal(sig1, binding_id="b1", quantity=100)
        i2 = OrderIntent.from_signal(sig2, binding_id="b1", quantity=100)
        assert i1.intent_id != i2.intent_id

    def test_invalid_quantity_raises(self) -> None:
        signal = _signal("sig-001")
        with pytest.raises(ValueError, match="quantity must be positive"):
            OrderIntent.from_signal(signal, binding_id="b1", quantity=0)

    def test_frozen(self) -> None:
        signal = _signal("sig-001")
        intent = OrderIntent.from_signal(signal, binding_id="b1", quantity=100)
        with pytest.raises(AttributeError):
            intent.quantity = 200
