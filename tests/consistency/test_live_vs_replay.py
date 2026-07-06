"""Live vs replay consistency assertions."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from quant_signal_system.contracts.signals import (
    Direction,
    ExecutionStatus,
    ExposureEffect,
    SignalAction,
    SignalEvent,
)
from tests.helpers.orchestration import OrchestrationHarness, generate_bars, utc


def _event(signal_id: str, direction: Direction) -> SignalEvent:
    market_time = utc(2025, 6, 2, 9, 30)
    now = market_time
    from quant_signal_system.contracts.features import FeatureSnapshot

    snap = FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id=f"fs-{signal_id}",
        symbol="300346",
        market_data_time=market_time,
        generated_at=market_time,
        feature_version="f1",
        lookback_window="3bars",
        features={"close": 42.0},
        missing_data_flags=(),
        input_bar_range="2025-06-02T09:29:00..2025-06-02T09:31:00",
    )
    return SignalEvent(
        schema_version="signal-event-v1",
        signal_id=signal_id,
        symbol="300346",
        direction=direction,
        signal_action=SignalAction.BUY if direction == Direction.BUY else SignalAction.RISK_AVOID,
        exposure_effect=ExposureEffect.INCREASE_LONG,
        event_time=now,
        market_data_time=market_time,
        ingest_time=now,
        executable_time=now,
        reference_price=None,
        executable_price=None,
        executable_price_source=None,
        execution_status=ExecutionStatus.UNKNOWN_AT_EVENT_TIME,
        unexecutable_reason=None,
        score=None,
        confidence=None,
        horizon_seconds=900,
        reason_codes=(),
        invalid_condition=None,
        feature_snapshot=snap,
        market_regime=None,
        strategy_name="rule_vol_breakout",
        strategy_version="v1",
        feature_version="f1",
        code_version="cv1",
        parameter_hash="ph1",
        data_source_version="test-v1",
        as_of_version="asof-v1",
        created_at=now,
    )


def _replay_signal_ids(bars: Iterable) -> tuple[str, ...]:
    harness = OrchestrationHarness(symbols=("300346",))
    return harness.run(list(bars)).signal_ids


def _assert_signal_count(min_count: int = 1) -> tuple[str, ...]:
    """Run a deterministic setup that produces at least ``min_count`` signals.

    The factory synthesises wide volume and price swings so the
    ``RuleStrategyRuntime`` actually fires; without it the default bars
    generate zero signals which makes the reconciliation tests vacuous.
    """
    from datetime import timedelta

    start = utc(2025, 6, 2, 9, 30)
    bars: list = []
    import random

    rng = random.Random(7)
    for i in range(30):
        bars.append(
            make_bar_with_volume(
                symbol="300346",
                market_data_time=start + timedelta(minutes=i),
                close=42.0 + rng.uniform(-2, 2),
                volume=2000 + rng.choice([0, 4000, 8000]),
            )
        )
    ids = _replay_signal_ids(bars)
    assert ids, "expected fixture to produce at least one signal"
    return ids


def make_bar_with_volume(symbol: str, market_data_time, *, close: float, volume: int):
    """Forwarder to ``tests.helpers.orchestration.make_bar`` (kept for legacy imports)."""
    from tests.helpers.orchestration import make_bar

    return make_bar(symbol, market_data_time, close=close, volume=volume)


class TestLiveVsReplay:
    """When shadow and replay disagree we expect the comparator to surface diffs."""

    def test_replay_deterministic(self) -> None:
        bars = generate_bars("300346", 60)
        assert _replay_signal_ids(bars) == _replay_signal_ids(bars)

    def test_shadow_perfectly_matches(self) -> None:
        from quant_signal_system.reporting.reconciliation import ShadowRunComparator

        ids = _assert_signal_count()
        replay_events = [_event(sid, Direction.BUY) for sid in ids]
        shadow_events = [_event(sid, Direction.BUY) for sid in ids]

        report = ShadowRunComparator().compare(
            replay_signals=replay_events,
            shadow_signals=shadow_events,
        )
        assert report.missing_in_shadow == ()
        assert report.extra_in_shadow == ()
        assert report.direction_mismatches == ()
        assert report.unexplained_differences == 0

    def test_shadow_missing_one_signal(self) -> None:
        from quant_signal_system.reporting.reconciliation import ShadowRunComparator

        ids = _assert_signal_count()
        replay_events = [_event(sid, Direction.BUY) for sid in ids]
        shadow_events = [_event(sid, Direction.BUY) for sid in ids[:-1]]  # drop last

        report = ShadowRunComparator().compare(
            replay_signals=replay_events,
            shadow_signals=shadow_events,
        )
        assert len(report.missing_in_shadow) == 1

    def test_shadow_extra_one_signal(self) -> None:
        from quant_signal_system.reporting.reconciliation import ShadowRunComparator

        ids = _assert_signal_count()
        replay_events = [_event(sid, Direction.BUY) for sid in ids]
        shadow_events = replay_events + [_event("phantom-signal", Direction.BUY)]

        report = ShadowRunComparator().compare(
            replay_signals=replay_events,
            shadow_signals=shadow_events,
        )
        assert len(report.extra_in_shadow) == 1

    def test_shadow_direction_mismatch(self) -> None:
        from quant_signal_system.reporting.reconciliation import ShadowRunComparator

        ids = _assert_signal_count()
        replay_events = [_event(sid, Direction.BUY) for sid in ids]
        shadow_events = [
            _event(sid, Direction.SELL if i == 0 else Direction.BUY) for i, sid in enumerate(ids)
        ]

        report = ShadowRunComparator().compare(
            replay_signals=replay_events,
            shadow_signals=shadow_events,
        )
        assert len(report.direction_mismatches) == 1
