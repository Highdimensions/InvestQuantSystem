"""Evaluation task generation and leasing."""

from __future__ import annotations

from dataclasses import dataclass

from quant_signal_system.contracts.evaluation import EvaluationPolicy, EvaluationTask
from quant_signal_system.contracts.signals import SignalEvent
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.time.clock import Clock
from quant_signal_system.time.trading_calendar import SimpleAshareTradingCalendar


@dataclass(frozen=True, slots=True)
class EvaluationScheduler:
    repository: InMemorySignalRepository
    clock: Clock
    calendar: SimpleAshareTradingCalendar
    policy: EvaluationPolicy = EvaluationPolicy()

    def create_tasks_for_signal(self, signal: SignalEvent) -> list[EvaluationTask]:
        self.policy.validate()
        tasks: list[EvaluationTask] = []
        for horizon in self.policy.horizons_seconds:
            due_time = self.calendar.next_evaluation_time(signal.event_time, horizon, signal.symbol)
            task = EvaluationTask(
                signal_id=signal.signal_id,
                horizon_seconds=horizon,
                due_time=due_time,
                evaluation_policy_version=self.policy.policy_version,
                data_source_version=signal.data_source_version,
                as_of_version=signal.as_of_version,
            )
            self.repository.upsert_task(task)
            tasks.append(task)
        return tasks

    def find_due_tasks(self) -> list[EvaluationTask]:
        return self.repository.find_due_tasks(self.clock.now())

    def claim(self, task: EvaluationTask, *, worker_id: str, lease_seconds: int = 60) -> EvaluationTask:
        return self.repository.claim(
            task.task_key,
            worker_id=worker_id,
            now=self.clock.now(),
            lease_seconds=lease_seconds,
        )

