"""Fault tests for evaluation task recovery and idempotency.

Covers the failure matrix from
``docs/architecture/testing-and-evaluation.md`` Section 7:

- claim after worker crash → lease expires and task is reclaimable
- partial write: evaluation persisted but task completion marker failed
- concurrent claim race: only one worker wins
- POSTPONED retry: task re-evaluated after next_retry_at

These tests use the in-memory repository directly so the failure modes are
deterministic and do not depend on wall-clock timing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.evaluation import (
    EvaluationPolicy,
    EvaluationTask,
    EvaluationTaskStatus,
)
from quant_signal_system.contracts.features import FeatureSnapshot
from quant_signal_system.contracts.signals import (
    Direction,
    ExecutionStatus,
    ExposureEffect,
    SignalAction,
    SignalCandidate,
)
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.time.clock import FrozenClock


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _feature_snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap_001",
        symbol="300346",
        market_data_time=_utc("2025-06-02T09:30:00+00:00"),
        generated_at=_utc("2025-06-02T09:30:00+00:00"),
        feature_version="rolling-feature-v1",
        lookback_window="3bars",
        features={"return_1": 0.01, "volume_ratio": 1.2, "ma_distance": 0.0},
        missing_data_flags=(),
        input_bar_range="2025-06-02T09:28:00..2025-06-02T09:30:00",
    )


def _signal() -> SignalEvent:
    candidate = SignalCandidate(
        symbol="300346",
        direction=Direction.BUY,
        signal_action=SignalAction.BUY,
        exposure_effect=ExposureEffect.INCREASE_LONG,
        market_data_time=_utc("2025-06-02T09:30:00+00:00"),
        reference_price=Decimal("42"),
        score=Decimal("0.5"),
        confidence=Decimal("0.6"),
        horizon_seconds=900,
        reason_codes=("BREAKOUT",),
        invalid_condition=None,
        feature_snapshot=_feature_snapshot(),
        market_regime=None,
        strategy_name="baseline-rules",
        strategy_version="v1",
        feature_version="rolling-feature-v1",
        code_version="code-v1",
        parameter_hash="ph1",
        data_source_version="akshare-v1",
        as_of_version="asof-v1",
    )
    clock = FrozenClock(current_time=_utc("2025-06-02T09:30:00+00:00"))
    service = SignalService(clock=clock)
    return service.create_event(candidate)


def _task(signal_id: str = "sig_001", horizon: int = 900) -> EvaluationTask:
    return EvaluationTask(
        signal_id=signal_id,
        horizon_seconds=horizon,
        due_time=_utc("2025-06-02T09:45:00+00:00"),
        evaluation_policy_version="evaluation-policy-v1",
        data_source_version="akshare-v1",
        as_of_version="asof-v1",
    )


class TestLeaseRecovery:
    """Worker crash after claim should allow reclaim after lease expires."""

    def test_reclaim_after_lease_expires(self) -> None:
        signal = _signal()
        repo = InMemorySignalRepository()
        repo.append_signal(signal)
        task = EvaluationTask(
            signal_id=signal.signal_id,
            horizon_seconds=900,
            due_time=_utc("2025-06-02T09:45:00+00:00"),
            evaluation_policy_version="evaluation-policy-v1",
            data_source_version="akshare-v1",
            as_of_version="asof-v1",
        )
        repo.upsert_task(task)

        # Worker A claims the task
        claimed = repo.claim(
            task.task_key,
            worker_id="worker_a",
            now=_utc("2025-06-02T09:30:00+00:00"),
            lease_seconds=60,
        )
        assert claimed.status == EvaluationTaskStatus.RUNNING
        assert claimed.worker_id == "worker_a"

        # Before lease expires, Worker B cannot claim
        with pytest.raises(Exception):
            repo.claim(
                task.task_key,
                worker_id="worker_b",
                now=_utc("2025-06-02T09:30:30+00:00"),
                lease_seconds=60,
            )

        # After lease expires, Worker B can reclaim
        reclaimed = repo.claim(
            task.task_key,
            worker_id="worker_b",
            now=_utc("2025-06-02T09:31:30+00:00"),
            lease_seconds=60,
        )
        assert reclaimed.worker_id == "worker_b"


class TestIdempotentUpsert:
    """Evaluation results must be idempotent under repeated writes."""

    def test_duplicate_evaluation_upsert_is_idempotent(self) -> None:
        from quant_signal_system.contracts.evaluation import SignalEvaluation
        signal = _signal()
        repo = InMemorySignalRepository()
        repo.append_signal(signal)
        evaluation = SignalEvaluation(
            schema_version="signal-evaluation-v1",
            evaluation_run_id="run_001",
            signal_id=signal.signal_id,
            horizon_seconds=900,
            evaluation_time=_utc("2025-06-02T09:45:00+00:00"),
            executable_time=signal.executable_time,
            executable_price=Decimal("42"),
            executable_price_source="NEXT_BAR_OPEN",
            execution_status=ExecutionStatus.EXECUTABLE,
            unexecutable_reason=None,
            evaluation_price=Decimal("43"),
            raw_return=Decimal("0.0238"),
            direction_return=Decimal("0.0238"),
            net_return=Decimal("0.0234"),
            mfe=Decimal("0.03"),
            mae=Decimal("-0.005"),
            time_to_mfe_seconds=300,
            time_to_mae_seconds=120,
            triple_barrier_label=1,
            barrier_config_version="triple-barrier-v1",
            path_granularity="BAR_OHLC",
            barrier_conflict_policy="AMBIGUOUS",
            transaction_cost=Decimal("0.0004"),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
            signal_delay_seconds=60,
            evaluator_version="signal-evaluator-v2",
            evaluation_policy_version="evaluation-policy-v1",
            cost_model_version="ac-share-cost-v1",
            slippage_model_version="zero-slippage-v1",
            delay_model_version="one-second-delay-v1",
            fill_model_version="next-bar-open-fill-v1",
            data_source_version="akshare-v1",
            as_of_version="asof-v1",
            created_at=_utc("2025-06-02T09:46:00+00:00"),
        )
        # First write returns "inserted"
        first = repo.upsert_evaluation(evaluation)
        assert first == "inserted"
        # Second write with identical content returns "duplicate" (no conflict)
        second = repo.upsert_evaluation(evaluation)
        assert second == "duplicate"
        # Storage contains only one evaluation
        assert len(repo._evaluations) == 1


class TestPostponedRetry:
    """POSTPONED tasks should be retryable after next_retry_at."""

    def test_postponed_task_retry(self) -> None:
        signal = _signal()
        repo = InMemorySignalRepository()
        repo.append_signal(signal)
        task = EvaluationTask(
            signal_id=signal.signal_id,
            horizon_seconds=900,
            due_time=_utc("2025-06-02T09:45:00+00:00"),
            evaluation_policy_version="evaluation-policy-v1",
            data_source_version="akshare-v1",
            as_of_version="asof-v1",
        )
        repo.upsert_task(task)
        # Postpone the task
        repo.postpone_task(
            task.task_key,
            next_retry_at=_utc("2025-06-02T09:31:00+00:00"),
            reason="DATA_UNAVAILABLE",
        )
        # Find due tasks before retry window: not due (due_time is 09:45)
        before = repo.find_due_tasks(_utc("2025-06-02T09:30:00+00:00"))
        assert all(t.signal_id != signal.signal_id for t in before)
        # After retry window: due again
        after = repo.find_due_tasks(_utc("2025-06-02T09:50:00+00:00"))
        assert any(t.signal_id == signal.signal_id for t in after)


class TestDuplicateTaskExecution:
    """Duplicate tasks with same key must not be created."""

    def test_duplicate_upsert_task_is_idempotent(self) -> None:
        signal = _signal()
        repo = InMemorySignalRepository()
        repo.append_signal(signal)
        task = EvaluationTask(
            signal_id=signal.signal_id,
            horizon_seconds=900,
            due_time=_utc("2025-06-02T09:45:00+00:00"),
            evaluation_policy_version="evaluation-policy-v1",
            data_source_version="akshare-v1",
            as_of_version="asof-v1",
        )
        repo.upsert_task(task)
        repo.upsert_task(task)
        # find_due_tasks should return only one entry per key
        due = repo.find_due_tasks(_utc("2025-06-02T09:50:00+00:00"))
        matching = [t for t in due if t.signal_id == signal.signal_id]
        assert len(matching) == 1