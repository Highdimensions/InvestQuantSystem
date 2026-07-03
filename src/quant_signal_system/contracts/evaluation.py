"""Evaluation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc
from quant_signal_system.contracts.signals import ExecutionStatus


class EvaluationTaskStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    POSTPONED = "POSTPONED"
    FAILED = "FAILED"
    CENSORED = "CENSORED"


class BarrierConflictPolicy(StrEnum):
    CONSERVATIVE = "CONSERVATIVE"
    AMBIGUOUS = "AMBIGUOUS"
    REQUIRE_TICK = "REQUIRE_TICK"


class PathGranularity(StrEnum):
    TICK = "TICK"
    BAR_OHLC = "BAR_OHLC"
    BAR_CLOSE = "BAR_CLOSE"


@dataclass(frozen=True, slots=True)
class EvaluationPolicy:
    policy_version: str = "evaluation-policy-v1"
    horizons_seconds: tuple[int, ...] = (300, 900, 1800, 3600)
    max_postpone_seconds: int = 3 * 24 * 60 * 60
    barrier_conflict_policy: BarrierConflictPolicy = BarrierConflictPolicy.AMBIGUOUS

    def validate(self) -> None:
        if not self.policy_version:
            raise MarketDataValidationError("policy_version is required")
        if not self.horizons_seconds or any(value <= 0 for value in self.horizons_seconds):
            raise MarketDataValidationError("horizons_seconds must be positive")


@dataclass(frozen=True, slots=True)
class EvaluationTask:
    signal_id: str
    horizon_seconds: int
    due_time: datetime
    evaluation_policy_version: str
    data_source_version: str
    as_of_version: str
    status: EvaluationTaskStatus = EvaluationTaskStatus.PENDING
    claimed_at: datetime | None = None
    lease_expires_at: datetime | None = None
    worker_id: str | None = None
    attempts: int = 0
    next_retry_at: datetime | None = None
    last_error: str | None = None

    @property
    def task_key(self) -> tuple[str, int, str, str, str]:
        return (
            self.signal_id,
            self.horizon_seconds,
            self.evaluation_policy_version,
            self.data_source_version,
            self.as_of_version,
        )

    def validate(self) -> None:
        require_aware_utc(self.due_time, "due_time")
        if not self.signal_id or self.horizon_seconds <= 0:
            raise MarketDataValidationError("evaluation task identity is invalid")


@dataclass(frozen=True, slots=True)
class SignalEvaluation:
    schema_version: str
    evaluation_run_id: str
    signal_id: str
    horizon_seconds: int
    evaluation_time: datetime
    executable_time: datetime
    executable_price: Decimal | None
    executable_price_source: str | None
    execution_status: ExecutionStatus
    unexecutable_reason: str | None
    evaluation_price: Decimal | None
    raw_return: Decimal | None
    direction_return: Decimal | None
    net_return: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    time_to_mfe_seconds: int | None
    time_to_mae_seconds: int | None
    triple_barrier_label: int | None
    barrier_config_version: str
    path_granularity: PathGranularity
    barrier_conflict_policy: BarrierConflictPolicy
    transaction_cost: Decimal
    slippage: Decimal
    spread_cost: Decimal
    signal_delay_seconds: int
    evaluator_version: str
    evaluation_policy_version: str
    cost_model_version: str
    slippage_model_version: str
    delay_model_version: str
    fill_model_version: str
    data_source_version: str
    as_of_version: str
    created_at: datetime
    status: EvaluationTaskStatus = EvaluationTaskStatus.COMPLETED

    @property
    def evaluation_key(self) -> tuple[str, int, str, str, str, str, str, str]:
        return (
            self.signal_id,
            self.horizon_seconds,
            self.evaluation_policy_version,
            self.evaluator_version,
            self.cost_model_version,
            self.fill_model_version,
            self.data_source_version,
            self.as_of_version,
        )

    def validate(self) -> None:
        require_aware_utc(self.evaluation_time, "evaluation_time")
        require_aware_utc(self.executable_time, "executable_time")
        require_aware_utc(self.created_at, "created_at")
        if self.horizon_seconds <= 0:
            raise MarketDataValidationError("horizon_seconds must be positive")
        if self.status == EvaluationTaskStatus.COMPLETED and self.evaluation_price is None:
            raise MarketDataValidationError("completed evaluation requires evaluation_price")

