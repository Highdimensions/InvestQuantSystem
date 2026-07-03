"""SQLite-backed append-only repository for signals, tasks, and evaluations."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from quant_signal_system.contracts.evaluation import (
    BarrierConflictPolicy,
    EvaluationTask,
    EvaluationTaskStatus,
    PathGranularity,
    SignalEvaluation,
)
from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.contracts.signals import (
    Direction,
    ExecutionStatus,
    ExposureEffect,
    SignalAction,
    SignalEvent,
)
from quant_signal_system.signals.repository import SignalConflictError


def _json_default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"cannot serialize {type(value)!r}")


def _payload(value: object) -> str:
    return json.dumps(asdict(value), default=_json_default, ensure_ascii=False, sort_keys=True)


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def _feature_from_dict(payload: dict[str, Any]) -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version=payload["schema_version"],
        feature_snapshot_id=payload["feature_snapshot_id"],
        symbol=payload["symbol"],
        market_data_time=_datetime(payload["market_data_time"]),
        generated_at=_datetime(payload["generated_at"]),
        feature_version=payload["feature_version"],
        lookback_window=payload["lookback_window"],
        features=payload["features"],
        missing_data_flags=tuple(payload.get("missing_data_flags", ())),
        input_bar_range=payload["input_bar_range"],
    )


def _regime_from_dict(payload: dict[str, Any] | None) -> MarketRegime | None:
    if payload is None:
        return None
    return MarketRegime(
        schema_version=payload["schema_version"],
        symbol=payload["symbol"],
        market_data_time=_datetime(payload["market_data_time"]),
        generated_at=_datetime(payload["generated_at"]),
        regime_version=payload["regime_version"],
        regime_label=payload["regime_label"],
        confidence=payload["confidence"],
        inputs=payload["inputs"],
        as_of_version=payload["as_of_version"],
        unavailable_inputs=tuple(payload.get("unavailable_inputs", ())),
    )


def signal_event_from_json(text: str) -> SignalEvent:
    payload = json.loads(text)
    return SignalEvent(
        schema_version=payload["schema_version"],
        signal_id=payload["signal_id"],
        symbol=payload["symbol"],
        direction=Direction(payload["direction"]),
        signal_action=SignalAction(payload["signal_action"]),
        exposure_effect=ExposureEffect(payload["exposure_effect"]),
        event_time=_datetime(payload["event_time"]),
        market_data_time=_datetime(payload["market_data_time"]),
        ingest_time=_datetime(payload["ingest_time"]),
        executable_time=_datetime(payload["executable_time"]),
        reference_price=Decimal(payload["reference_price"]),
        executable_price=_decimal(payload["executable_price"]),
        executable_price_source=payload["executable_price_source"],
        execution_status=ExecutionStatus(payload["execution_status"]),
        unexecutable_reason=payload["unexecutable_reason"],
        score=Decimal(payload["score"]),
        confidence=Decimal(payload["confidence"]),
        horizon_seconds=int(payload["horizon_seconds"]),
        reason_codes=tuple(payload.get("reason_codes", ())),
        invalid_condition=payload["invalid_condition"],
        feature_snapshot=_feature_from_dict(payload["feature_snapshot"]),
        market_regime=_regime_from_dict(payload["market_regime"]),
        strategy_name=payload["strategy_name"],
        strategy_version=payload["strategy_version"],
        feature_version=payload["feature_version"],
        code_version=payload["code_version"],
        parameter_hash=payload["parameter_hash"],
        data_source_version=payload["data_source_version"],
        as_of_version=payload["as_of_version"],
        created_at=_datetime(payload["created_at"]),
    )


def evaluation_from_json(text: str) -> SignalEvaluation:
    payload = json.loads(text)
    return SignalEvaluation(
        schema_version=payload["schema_version"],
        evaluation_run_id=payload["evaluation_run_id"],
        signal_id=payload["signal_id"],
        horizon_seconds=int(payload["horizon_seconds"]),
        evaluation_time=_datetime(payload["evaluation_time"]),
        executable_time=_datetime(payload["executable_time"]),
        executable_price=_decimal(payload["executable_price"]),
        executable_price_source=payload["executable_price_source"],
        execution_status=ExecutionStatus(payload["execution_status"]),
        unexecutable_reason=payload["unexecutable_reason"],
        evaluation_price=_decimal(payload["evaluation_price"]),
        raw_return=_decimal(payload["raw_return"]),
        direction_return=_decimal(payload["direction_return"]),
        net_return=_decimal(payload["net_return"]),
        mfe=_decimal(payload["mfe"]),
        mae=_decimal(payload["mae"]),
        time_to_mfe_seconds=payload["time_to_mfe_seconds"],
        time_to_mae_seconds=payload["time_to_mae_seconds"],
        triple_barrier_label=payload["triple_barrier_label"],
        barrier_config_version=payload["barrier_config_version"],
        path_granularity=PathGranularity(payload["path_granularity"]),
        barrier_conflict_policy=BarrierConflictPolicy(payload["barrier_conflict_policy"]),
        transaction_cost=Decimal(payload["transaction_cost"]),
        slippage=Decimal(payload["slippage"]),
        spread_cost=Decimal(payload["spread_cost"]),
        signal_delay_seconds=int(payload["signal_delay_seconds"]),
        evaluator_version=payload["evaluator_version"],
        evaluation_policy_version=payload["evaluation_policy_version"],
        cost_model_version=payload["cost_model_version"],
        slippage_model_version=payload["slippage_model_version"],
        delay_model_version=payload["delay_model_version"],
        fill_model_version=payload["fill_model_version"],
        data_source_version=payload["data_source_version"],
        as_of_version=payload["as_of_version"],
        created_at=_datetime(payload["created_at"]),
        status=EvaluationTaskStatus(payload["status"]),
    )


def task_from_json(text: str) -> EvaluationTask:
    payload = json.loads(text)
    return EvaluationTask(
        signal_id=payload["signal_id"],
        horizon_seconds=int(payload["horizon_seconds"]),
        due_time=_datetime(payload["due_time"]),
        evaluation_policy_version=payload["evaluation_policy_version"],
        data_source_version=payload["data_source_version"],
        as_of_version=payload["as_of_version"],
        status=EvaluationTaskStatus(payload["status"]),
        claimed_at=None if payload["claimed_at"] is None else _datetime(payload["claimed_at"]),
        lease_expires_at=None
        if payload["lease_expires_at"] is None
        else _datetime(payload["lease_expires_at"]),
        worker_id=payload["worker_id"],
        attempts=int(payload["attempts"]),
        next_retry_at=None if payload["next_retry_at"] is None else _datetime(payload["next_retry_at"]),
        last_error=payload["last_error"],
    )


@dataclass(slots=True)
class SQLiteSignalRepository:
    database_path: str | Path

    def __post_init__(self) -> None:
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.database_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    strategy_name TEXT NOT NULL,
                    strategy_version TEXT NOT NULL,
                    direction INTEGER NOT NULL,
                    signal_action TEXT NOT NULL,
                    event_time TEXT NOT NULL,
                    market_data_time TEXT NOT NULL,
                    data_source_version TEXT NOT NULL,
                    as_of_version TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluation_tasks (
                    signal_id TEXT NOT NULL,
                    horizon_seconds INTEGER NOT NULL,
                    evaluation_policy_version TEXT NOT NULL,
                    data_source_version TEXT NOT NULL,
                    as_of_version TEXT NOT NULL,
                    due_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (
                        signal_id, horizon_seconds, evaluation_policy_version,
                        data_source_version, as_of_version
                    )
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS signal_evaluations (
                    signal_id TEXT NOT NULL,
                    horizon_seconds INTEGER NOT NULL,
                    evaluation_policy_version TEXT NOT NULL,
                    evaluator_version TEXT NOT NULL,
                    cost_model_version TEXT NOT NULL,
                    fill_model_version TEXT NOT NULL,
                    data_source_version TEXT NOT NULL,
                    as_of_version TEXT NOT NULL,
                    evaluation_time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (
                        signal_id, horizon_seconds, evaluation_policy_version,
                        evaluator_version, cost_model_version, fill_model_version,
                        data_source_version, as_of_version
                    )
                )
                """
            )

    def append_signal(self, event: SignalEvent) -> str:
        event.validate()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM signals WHERE signal_id = ?",
                (event.signal_id,),
            ).fetchone()
            if row is not None:
                if signal_event_from_json(row["payload"]) == event:
                    return event.signal_id
                raise SignalConflictError("SignalEvent append-only conflict")
            conn.execute(
                """
                INSERT INTO signals (
                    signal_id, symbol, strategy_name, strategy_version, direction,
                    signal_action, event_time, market_data_time, data_source_version,
                    as_of_version, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.signal_id,
                    event.symbol,
                    event.strategy_name,
                    event.strategy_version,
                    int(event.direction),
                    event.signal_action.value,
                    event.event_time.isoformat(),
                    event.market_data_time.isoformat(),
                    event.data_source_version,
                    event.as_of_version,
                    _payload(event),
                ),
            )
        return event.signal_id

    def get_signal(self, signal_id: str) -> SignalEvent:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM signals WHERE signal_id = ?",
                (signal_id,),
            ).fetchone()
        if row is None:
            raise KeyError(signal_id)
        return signal_event_from_json(row["payload"])

    def list_signals(
        self,
        *,
        symbol: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        strategy_versions: tuple[str, ...] = (),
    ) -> list[SignalEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if from_time:
            clauses.append("market_data_time >= ?")
            params.append(from_time.isoformat())
        if to_time:
            clauses.append("market_data_time <= ?")
            params.append(to_time.isoformat())
        if strategy_versions:
            placeholders = ", ".join("?" for _ in strategy_versions)
            clauses.append(f"strategy_version IN ({placeholders})")
            params.extend(strategy_versions)
        where = "" if not clauses else "WHERE " + " AND ".join(clauses)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT payload FROM signals {where} ORDER BY market_data_time ASC",
                params,
            ).fetchall()
        return [signal_event_from_json(row["payload"]) for row in rows]

    def upsert_task(self, task: EvaluationTask) -> None:
        task.validate()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO evaluation_tasks (
                    signal_id, horizon_seconds, evaluation_policy_version,
                    data_source_version, as_of_version, due_time, status, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.signal_id,
                    task.horizon_seconds,
                    task.evaluation_policy_version,
                    task.data_source_version,
                    task.as_of_version,
                    task.due_time.isoformat(),
                    task.status.value,
                    _payload(task),
                ),
            )

    def find_due_tasks(self, now: datetime) -> list[EvaluationTask]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM evaluation_tasks
                WHERE due_time <= ?
                  AND status IN (?, ?)
                ORDER BY due_time ASC
                """,
                (
                    now.isoformat(),
                    EvaluationTaskStatus.PENDING.value,
                    EvaluationTaskStatus.POSTPONED.value,
                ),
            ).fetchall()
        return [
            task
            for task in (task_from_json(row["payload"]) for row in rows)
            if task.next_retry_at is None or task.next_retry_at <= now
        ]

    def find_expired_leases(self, now: datetime) -> list[EvaluationTask]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM evaluation_tasks
                WHERE status = ?
                """,
                (EvaluationTaskStatus.RUNNING.value,),
            ).fetchall()
        return [
            task
            for task in (task_from_json(row["payload"]) for row in rows)
            if task.lease_expires_at is not None and task.lease_expires_at <= now
        ]

    def claim(
        self,
        task_key: tuple[str, int, str, str, str],
        *,
        worker_id: str,
        now: datetime,
        lease_seconds: int,
    ) -> EvaluationTask:
        from dataclasses import replace
        from datetime import timedelta

        task = self._get_task(task_key)
        if (
            task.status == EvaluationTaskStatus.RUNNING
            and task.lease_expires_at is not None
            and task.lease_expires_at > now
        ):
            raise SignalConflictError("task lease is still active")
        claimed = replace(
            task,
            status=EvaluationTaskStatus.RUNNING,
            claimed_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            worker_id=worker_id,
            attempts=task.attempts + 1,
        )
        self._replace_task(claimed)
        return claimed

    def complete_task(self, task_key: tuple[str, int, str, str, str]) -> None:
        from dataclasses import replace

        self._replace_task(replace(self._get_task(task_key), status=EvaluationTaskStatus.COMPLETED))

    def postpone_task(
        self,
        task_key: tuple[str, int, str, str, str],
        *,
        next_retry_at: datetime,
        reason: str,
    ) -> None:
        from dataclasses import replace

        self._replace_task(
            replace(
                self._get_task(task_key),
                status=EvaluationTaskStatus.POSTPONED,
                next_retry_at=next_retry_at,
                last_error=reason,
            )
        )

    def upsert_evaluation(self, evaluation: SignalEvaluation) -> str:
        evaluation.validate()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM signal_evaluations
                WHERE signal_id = ? AND horizon_seconds = ?
                  AND evaluation_policy_version = ? AND evaluator_version = ?
                  AND cost_model_version = ? AND fill_model_version = ?
                  AND data_source_version = ? AND as_of_version = ?
                """,
                evaluation.evaluation_key,
            ).fetchone()
            if row is not None:
                if evaluation_from_json(row["payload"]) == evaluation:
                    return "duplicate"
                raise SignalConflictError("SignalEvaluation idempotency conflict")
            conn.execute(
                """
                INSERT INTO signal_evaluations (
                    signal_id, horizon_seconds, evaluation_policy_version,
                    evaluator_version, cost_model_version, fill_model_version,
                    data_source_version, as_of_version, evaluation_time, status, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    *evaluation.evaluation_key,
                    evaluation.evaluation_time.isoformat(),
                    evaluation.status.value,
                    _payload(evaluation),
                ),
            )
        return "inserted"

    def list_evaluations(self, *, signal_ids: tuple[str, ...] = ()) -> list[SignalEvaluation]:
        where = ""
        params: list[object] = []
        if signal_ids:
            placeholders = ", ".join("?" for _ in signal_ids)
            where = f"WHERE signal_id IN ({placeholders})"
            params.extend(signal_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT payload FROM signal_evaluations {where} ORDER BY evaluation_time ASC",
                params,
            ).fetchall()
        return [evaluation_from_json(row["payload"]) for row in rows]

    def strategy_counts(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT strategy_name, strategy_version, COUNT(*) AS sample_count,
                       MIN(market_data_time) AS first_market_data_time,
                       MAX(market_data_time) AS last_market_data_time
                FROM signals
                GROUP BY strategy_name, strategy_version
                ORDER BY strategy_name, strategy_version
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def _get_task(self, task_key: tuple[str, int, str, str, str]) -> EvaluationTask:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM evaluation_tasks
                WHERE signal_id = ? AND horizon_seconds = ?
                  AND evaluation_policy_version = ?
                  AND data_source_version = ? AND as_of_version = ?
                """,
                task_key,
            ).fetchone()
        if row is None:
            raise KeyError(task_key)
        return task_from_json(row["payload"])

    def _replace_task(self, task: EvaluationTask) -> None:
        task.validate()
        if task.next_retry_at is not None and task.next_retry_at.tzinfo is None:
            raise MarketDataValidationError("next_retry_at must be timezone-aware")
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE evaluation_tasks
                SET due_time = ?, status = ?, payload = ?
                WHERE signal_id = ? AND horizon_seconds = ?
                  AND evaluation_policy_version = ?
                  AND data_source_version = ? AND as_of_version = ?
                """,
                (
                    task.due_time.isoformat(),
                    task.status.value,
                    _payload(task),
                    *task.task_key,
                ),
            )
