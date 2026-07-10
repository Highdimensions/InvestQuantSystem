"""Test that deterministic_signal_id is idempotent across runs."""

from datetime import datetime, timezone
from decimal import Decimal

from quant_signal_system.contracts.features import FeatureSnapshot
from quant_signal_system.contracts.signals import (
    Direction,
    SignalAction,
    ExposureEffect,
    SignalCandidate,
    deterministic_signal_id,
)


def test_signal_id_idempotency() -> None:
    """Verify same candidate produces same signal_id regardless of event_time."""
    snapshot = FeatureSnapshot(
        schema_version="v1",
        feature_snapshot_id="snap-1",
        symbol="300346",
        market_data_time=datetime(2026, 7, 3, 2, 16, tzinfo=timezone.utc),
        generated_at=datetime(2026, 7, 3, 2, 16, 1, tzinfo=timezone.utc),
        feature_version="f1",
        lookback_window="1h",
        features={"rsi": 35.5},
        missing_data_flags=(),
        input_bar_range="2026-07-03T02:00:00/2026-07-03T02:16:00",
    )

    candidate = SignalCandidate(
        symbol="300346",
        direction=Direction.BUY,
        signal_action=SignalAction.BUY,
        exposure_effect=ExposureEffect.INCREASE_LONG,
        market_data_time=datetime(2026, 7, 3, 2, 16, tzinfo=timezone.utc),
        reference_price=Decimal("10.5"),
        score=Decimal("0.8"),
        confidence=Decimal("0.9"),
        horizon_seconds=900,
        reason_codes=("rsi_oversold",),
        invalid_condition=None,
        feature_snapshot=snapshot,
        market_regime=None,
        strategy_name="baseline-rules",
        strategy_version="v1",
        feature_version="f1",
        code_version="c1",
        parameter_hash="p1",
        data_source_version="ds1",
        as_of_version="ao1",
    )

    # Same candidate, different event_times
    time1 = datetime(2026, 7, 3, 6, 29, 34, tzinfo=timezone.utc)
    time2 = datetime(2026, 7, 3, 6, 31, 25, tzinfo=timezone.utc)
    time3 = datetime(2026, 7, 10, 3, 24, 49, tzinfo=timezone.utc)

    id1 = deterministic_signal_id(candidate, event_time=time1)
    id2 = deterministic_signal_id(candidate, event_time=time2)
    id3 = deterministic_signal_id(candidate, event_time=time3)

    assert id1 == id2 == id3, f"Signal IDs should be identical: {id1}, {id2}, {id3}"
    print(f"PASS: All three event_times produce the same signal_id: {id1}")

    from dataclasses import dataclass, replace

    # Different candidate should produce different signal_id
    candidate2 = replace(candidate, direction=Direction.SELL)
    id4 = deterministic_signal_id(candidate2, event_time=time1)
    assert id1 != id4, f"Different directions should produce different signal_ids"
    print(f"PASS: Different direction produces different signal_id: {id4}")

    # Different market_data_time should produce different signal_id
    candidate3 = replace(
        candidate,
        market_data_time=datetime(2026, 7, 3, 2, 17, tzinfo=timezone.utc),
    )
    id5 = deterministic_signal_id(candidate3, event_time=time1)
    assert id1 != id5, f"Different market_data_times should produce different signal_ids"
    print(f"PASS: Different market_data_time produces different signal_id: {id5}")

    print("\nAll idempotency tests passed!")


if __name__ == "__main__":
    test_signal_id_idempotency()
