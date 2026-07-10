"""Signal evaluation using future, already-persisted MarketBar paths."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from quant_signal_system.contracts.evaluation import (
    BarrierConflictPolicy,
    EvaluationPolicy,
    EvaluationTask,
    EvaluationTaskStatus,
    PathGranularity,
    SignalEvaluation,
)
from quant_signal_system.contracts.signals import Direction, ExecutionStatus
from quant_signal_system.evaluation.acshare_cost_model import ACShareCostModel
from quant_signal_system.evaluation.cost_model import FixedBpsCostModel
from quant_signal_system.evaluation.fill_model import NextBarOpenFillModel
from quant_signal_system.evaluation.triple_barrier import (
    TripleBarrierConfig,
    detect_first_barrier_hit,
    TRIPLE_BARRIER_TIME_ONLY,
    TRIPLE_BARRIER_AMBIGUOUS,
)
from quant_signal_system.market_data.repository import InMemoryMarketDataRepository
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.time.clock import Clock


@dataclass(frozen=True, slots=True)
class SignalEvaluator:
    signal_repository: InMemorySignalRepository
    market_repository: InMemoryMarketDataRepository
    clock: Clock
    cost_model: ACShareCostModel = ACShareCostModel()
    fill_model: NextBarOpenFillModel = NextBarOpenFillModel()
    policy: EvaluationPolicy = EvaluationPolicy()
    barrier_config: TripleBarrierConfig | None = None
    evaluator_version: str = "signal-evaluator-v2"
    slippage_model_version: str = "zero-slippage-v1"
    barrier_config_version: str = "triple-barrier-v1"

    def evaluate(self, task: EvaluationTask, *, timeframe: str = "1m") -> SignalEvaluation:
        signal = self.signal_repository.get_signal(task.signal_id)
        path = self.market_repository.read_bars(
            symbol=signal.symbol,
            from_time=signal.executable_time,
            to_time=task.due_time,
            timeframe=timeframe,
            data_source_version=task.data_source_version,
            as_of_version=task.as_of_version,
        )
        if not path:
            return self._unavailable(task, "NO_EVALUATION_PRICE")

        fill = self.fill_model.fill(signal, path)
        if fill.execution_status != ExecutionStatus.EXECUTABLE or fill.executable_price is None:
            return self._unexecutable(task, fill)

        evaluation_bar = path[-1]
        evaluation_price = evaluation_bar.close_price
        raw_return = (evaluation_price - fill.executable_price) / fill.executable_price
        direction_return = Decimal(int(signal.direction)) * raw_return
        cost = self.cost_model.cost_rate(signal.direction)
        net_return = direction_return - cost
        mfe = max(
            Decimal(int(signal.direction)) * ((bar.high_price - fill.executable_price) / fill.executable_price)
            if signal.direction == Direction.BUY
            else Decimal(int(signal.direction)) * ((bar.low_price - fill.executable_price) / fill.executable_price)
            for bar in path
        )
        mae = min(
            Decimal(int(signal.direction)) * ((bar.low_price - fill.executable_price) / fill.executable_price)
            if signal.direction == Direction.BUY
            else Decimal(int(signal.direction)) * ((bar.high_price - fill.executable_price) / fill.executable_price)
            for bar in path
        )
        # Time to MFE / MAE
        time_to_mfe = self._time_to_extreme(path, fill.executable_price, signal.direction, prefer="max")
        time_to_mae = self._time_to_extreme(path, fill.executable_price, signal.direction, prefer="min")
        # Triple barrier detection
        barrier_label = TRIPLE_BARRIER_TIME_ONLY
        barrier_time: int | None = None
        if self.barrier_config is not None and self.barrier_config.has_price_barriers:
            barrier_label, barrier_time = detect_first_barrier_hit(
                executable_price=fill.executable_price,
                direction=int(signal.direction),
                path_bars=path,
                config=self.barrier_config,
            )
        return self._evaluation(
            task,
            status=EvaluationTaskStatus.COMPLETED,
            executable_time=signal.executable_time,
            executable_price=fill.executable_price,
            executable_price_source=fill.executable_price_source,
            execution_status=fill.execution_status,
            unexecutable_reason=None,
            evaluation_price=evaluation_price,
            raw_return=raw_return,
            direction_return=direction_return,
            net_return=net_return,
            mfe=mfe,
            mae=mae,
            time_to_mfe_seconds=time_to_mfe,
            time_to_mae_seconds=time_to_mae,
            triple_barrier_label=barrier_label,
            signal_delay_seconds=fill.signal_delay_seconds,
            barrier_config_version=self.barrier_config_version if self.barrier_config is not None else "no-barrier-v1",
            barrier_conflict_policy=(self.barrier_config.conflict_policy if self.barrier_config is not None else BarrierConflictPolicy.AMBIGUOUS),
        )

    def _time_to_extreme(self, path, executable_price: Decimal, direction: Direction, *, prefer: str) -> int | None:
        """Compute the time (in seconds from path start) when MFE or MAE was reached.

        Returns None when no bar advances beyond the executable price in the
        relevant direction (e.g. MFE = 0 for a monotonically losing path).
        """
        if not path:
            return None
        best: Decimal | None = None
        best_time: int | None = None
        for bar in path:
            if direction == Direction.BUY:
                delta = (bar.high_price - executable_price) / executable_price
            else:
                delta = (executable_price - bar.low_price) / executable_price
            update = False
            if best is None:
                update = True
            elif prefer == "max" and delta > best:
                update = True
            elif prefer == "min" and delta < best:
                update = True
            if update:
                best = delta
                best_time = int((bar.market_data_time - path[0].market_data_time).total_seconds())
        return best_time

    def _unavailable(self, task: EvaluationTask, reason: str) -> SignalEvaluation:
        signal = self.signal_repository.get_signal(task.signal_id)
        return self._evaluation(
            task,
            status=EvaluationTaskStatus.POSTPONED,
            executable_time=signal.executable_time,
            executable_price=None,
            executable_price_source=None,
            execution_status=ExecutionStatus.UNEXECUTABLE,
            unexecutable_reason=reason,
            evaluation_price=None,
            raw_return=None,
            direction_return=None,
            net_return=None,
            mfe=None,
            mae=None,
            time_to_mfe_seconds=None,
            time_to_mae_seconds=None,
            triple_barrier_label=None,
            signal_delay_seconds=0,
            barrier_config_version=self.barrier_config_version if self.barrier_config is not None else "no-barrier-v1",
            barrier_conflict_policy=(self.barrier_config.conflict_policy if self.barrier_config is not None else BarrierConflictPolicy.AMBIGUOUS),
        )

    def _unexecutable(self, task: EvaluationTask, fill) -> SignalEvaluation:
        signal = self.signal_repository.get_signal(task.signal_id)
        return self._evaluation(
            task,
            status=EvaluationTaskStatus.CENSORED,
            executable_time=signal.executable_time,
            executable_price=None,
            executable_price_source=None,
            execution_status=fill.execution_status,
            unexecutable_reason=fill.unexecutable_reason,
            evaluation_price=None,
            raw_return=None,
            direction_return=None,
            net_return=None,
            mfe=None,
            mae=None,
            time_to_mfe_seconds=None,
            time_to_mae_seconds=None,
            triple_barrier_label=None,
            signal_delay_seconds=fill.signal_delay_seconds,
            barrier_config_version=self.barrier_config_version if self.barrier_config is not None else "no-barrier-v1",
            barrier_conflict_policy=(self.barrier_config.conflict_policy if self.barrier_config is not None else BarrierConflictPolicy.AMBIGUOUS),
        )

    def _evaluation(
        self,
        task: EvaluationTask,
        *,
        status: EvaluationTaskStatus,
        executable_time: datetime,
        executable_price: Decimal | None,
        executable_price_source: str | None,
        execution_status: ExecutionStatus,
        unexecutable_reason: str | None,
        evaluation_price: Decimal | None,
        raw_return: Decimal | None,
        direction_return: Decimal | None,
        net_return: Decimal | None,
        mfe: Decimal | None,
        mae: Decimal | None,
        time_to_mfe_seconds: int | None,
        time_to_mae_seconds: int | None,
        triple_barrier_label: int | None,
        signal_delay_seconds: int,
        barrier_config_version: str,
        barrier_conflict_policy: BarrierConflictPolicy,
    ) -> SignalEvaluation:
        created_at = self.clock.now()
        signal = self.signal_repository.get_signal(task.signal_id)
        key = "|".join(
            [
                task.signal_id,
                str(task.horizon_seconds),
                self.evaluator_version,
                self.policy.policy_version,
                self.cost_model.cost_model_version,
                self.fill_model.fill_model_version,
                task.data_source_version,
                task.as_of_version,
            ]
        )
        return SignalEvaluation(
            schema_version="signal-evaluation-v1",
            evaluation_run_id=hashlib.sha256(key.encode("utf-8")).hexdigest()[:16],
            signal_id=task.signal_id,
            horizon_seconds=task.horizon_seconds,
            evaluation_time=task.due_time,
            executable_time=executable_time,
            executable_price=executable_price,
            executable_price_source=executable_price_source,
            execution_status=execution_status,
            unexecutable_reason=unexecutable_reason,
            evaluation_price=evaluation_price,
            raw_return=raw_return,
            direction_return=direction_return,
            net_return=net_return,
            mfe=mfe,
            mae=mae,
            time_to_mfe_seconds=time_to_mfe_seconds,
            time_to_mae_seconds=time_to_mae_seconds,
            triple_barrier_label=triple_barrier_label,
            barrier_config_version=barrier_config_version,
            path_granularity=PathGranularity.BAR_OHLC,
            barrier_conflict_policy=barrier_conflict_policy,
            transaction_cost=Decimal("0") if net_return is None else self.cost_model.cost_rate(signal.direction),
            slippage=Decimal("0"),
            spread_cost=Decimal("0"),
            signal_delay_seconds=signal_delay_seconds,
            evaluator_version=self.evaluator_version,
            evaluation_policy_version=self.policy.policy_version,
            cost_model_version=self.cost_model.cost_model_version,
            slippage_model_version=self.slippage_model_version,
            delay_model_version=self.fill_model.delay_model_version,
            fill_model_version=self.fill_model.fill_model_version,
            data_source_version=task.data_source_version,
            as_of_version=task.as_of_version,
            created_at=created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc),
            status=status,
        )
