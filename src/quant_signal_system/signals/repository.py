"""Append-only in-memory repository for signals, tasks, and evaluations."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from quant_signal_system.contracts.evaluation import (
    EvaluationTask,
    EvaluationTaskStatus,
    SignalEvaluation,
)
from quant_signal_system.contracts.signals import SignalEvent


class SignalConflictError(ValueError):
    pass


@dataclass(slots=True)
class InMemorySignalRepository:
    _signals: dict[str, SignalEvent] = field(default_factory=dict)
    _tasks: dict[tuple[str, int, str, str, str], EvaluationTask] = field(default_factory=dict)
    _evaluations: dict[tuple[str, int, str, str, str, str, str, str], SignalEvaluation] = field(
        default_factory=dict
    )

    def append_signal(self, event: SignalEvent) -> str:
        event.validate()
        existing = self._signals.get(event.signal_id)
        if existing is None:
            self._signals[event.signal_id] = event
            return event.signal_id
        if existing == event:
            return event.signal_id
        raise SignalConflictError("SignalEvent append-only conflict")

    def get_signal(self, signal_id: str) -> SignalEvent:
        return self._signals[signal_id]

    def list_signals(self) -> list[SignalEvent]:
        return sorted(self._signals.values(), key=lambda signal: signal.event_time)

    def upsert_task(self, task: EvaluationTask) -> None:
        task.validate()
        self._tasks.setdefault(task.task_key, task)

    def find_due_tasks(self, now: datetime) -> list[EvaluationTask]:
        return sorted(
            (
                task
                for task in self._tasks.values()
                if task.due_time <= now
                and task.status in {EvaluationTaskStatus.PENDING, EvaluationTaskStatus.POSTPONED}
                and (task.next_retry_at is None or task.next_retry_at <= now)
            ),
            key=lambda task: task.due_time,
        )

    def find_expired_leases(self, now: datetime) -> list[EvaluationTask]:
        return [
            task
            for task in self._tasks.values()
            if task.status == EvaluationTaskStatus.RUNNING
            and task.lease_expires_at is not None
            and task.lease_expires_at <= now
        ]

    def claim(
        self,
        task_key: tuple[str, int, str, str, str],
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> EvaluationTask:
        task = self._tasks[task_key]
        if task.status == EvaluationTaskStatus.RUNNING and task.lease_expires_at > now:
            raise SignalConflictError("task lease is still active")
        claimed = replace(
            task,
            status=EvaluationTaskStatus.RUNNING,
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            worker_id=worker_id,
            attempts=task.attempts + 1,
        )
        self._tasks[task_key] = claimed
        return claimed

    def complete_task(self, task_key: tuple[str, int, str, str, str]) -> None:
        task = self._tasks[task_key]
        self._tasks[task_key] = replace(task, status=EvaluationTaskStatus.COMPLETED)

    def postpone_task(
        self,
        task_key: tuple[str, int, str, str, str],
        *,
        next_retry_at: datetime,
        reason: str,
    ) -> None:
        task = self._tasks[task_key]
        self._tasks[task_key] = replace(
            task,
            status=EvaluationTaskStatus.POSTPONED,
            next_retry_at=next_retry_at,
            last_error=reason,
        )

    def upsert_evaluation(self, evaluation: SignalEvaluation) -> str:
        evaluation.validate()
        existing = self._evaluations.get(evaluation.evaluation_key)
        if existing is None:
            self._evaluations[evaluation.evaluation_key] = evaluation
            return "inserted"
        if existing == evaluation:
            return "duplicate"
        raise SignalConflictError("SignalEvaluation idempotency conflict")

    def list_evaluations(self) -> list[SignalEvaluation]:
        return sorted(self._evaluations.values(), key=lambda item: item.evaluation_time)

