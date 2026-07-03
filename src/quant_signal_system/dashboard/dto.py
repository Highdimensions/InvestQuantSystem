"""Dashboard JSON DTOs.

The dashboard DTOs are display projections. They do not mutate domain facts and
they intentionally keep strategy, feature, data, and evaluation versions visible.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from quant_signal_system.contracts.evaluation import SignalEvaluation
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.contracts.signals import Direction, SignalEvent


def _number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _time(value: datetime) -> str:
    return value.isoformat()


def json_ready(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class DashboardBar:
    symbol: str
    timeframe: str
    market_data_time: str
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float | None
    data_source_version: str
    as_of_version: str

    @classmethod
    def from_bar(cls, bar: MarketBar) -> "DashboardBar":
        return cls(
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            market_data_time=_time(bar.market_data_time),
            open_price=float(bar.open_price),
            high_price=float(bar.high_price),
            low_price=float(bar.low_price),
            close_price=float(bar.close_price),
            volume=_number(bar.volume),
            data_source_version=bar.data_source_version,
            as_of_version=bar.as_of_version,
        )


@dataclass(frozen=True, slots=True)
class DashboardSignalPoint:
    signal_id: str
    symbol: str
    direction: int
    direction_label: str
    signal_action: str
    sell_semantics: str | None
    event_time: str
    market_data_time: str
    executable_time: str
    reference_price: float
    strategy_name: str
    strategy_version: str
    score: float
    confidence: float
    reason_codes: tuple[str, ...]
    feature_version: str
    parameter_hash: str
    data_source_version: str
    as_of_version: str

    @classmethod
    def from_signal(cls, signal: SignalEvent) -> "DashboardSignalPoint":
        return cls(
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            direction=int(signal.direction),
            direction_label=_direction_label(signal.direction),
            signal_action=signal.signal_action.value,
            sell_semantics=(
                "A-share Sell is a risk-avoid/reduce/clear-long signal, not short selling."
                if signal.direction == Direction.SELL
                else None
            ),
            event_time=_time(signal.event_time),
            market_data_time=_time(signal.market_data_time),
            executable_time=_time(signal.executable_time),
            reference_price=float(signal.reference_price),
            strategy_name=signal.strategy_name,
            strategy_version=signal.strategy_version,
            score=float(signal.score),
            confidence=float(signal.confidence),
            reason_codes=signal.reason_codes,
            feature_version=signal.feature_version,
            parameter_hash=signal.parameter_hash,
            data_source_version=signal.data_source_version,
            as_of_version=signal.as_of_version,
        )


@dataclass(frozen=True, slots=True)
class DashboardEvaluationSummary:
    signal_id: str
    horizon_seconds: int
    status: str
    evaluation_time: str
    execution_status: str
    executable_price: float | None
    evaluation_price: float | None
    direction_return: float | None
    net_return: float | None
    mfe: float | None
    mae: float | None
    evaluation_policy_version: str
    evaluator_version: str
    cost_model_version: str
    fill_model_version: str
    data_source_version: str
    as_of_version: str

    @classmethod
    def from_evaluation(cls, evaluation: SignalEvaluation) -> "DashboardEvaluationSummary":
        return cls(
            signal_id=evaluation.signal_id,
            horizon_seconds=evaluation.horizon_seconds,
            status=evaluation.status.value,
            evaluation_time=_time(evaluation.evaluation_time),
            execution_status=evaluation.execution_status.value,
            executable_price=_number(evaluation.executable_price),
            evaluation_price=_number(evaluation.evaluation_price),
            direction_return=_number(evaluation.direction_return),
            net_return=_number(evaluation.net_return),
            mfe=_number(evaluation.mfe),
            mae=_number(evaluation.mae),
            evaluation_policy_version=evaluation.evaluation_policy_version,
            evaluator_version=evaluation.evaluator_version,
            cost_model_version=evaluation.cost_model_version,
            fill_model_version=evaluation.fill_model_version,
            data_source_version=evaluation.data_source_version,
            as_of_version=evaluation.as_of_version,
        )


def dto_dict(value: object) -> dict[str, Any]:
    return json_ready(asdict(value))  # type: ignore[arg-type]


def _direction_label(direction: Direction) -> str:
    if direction == Direction.BUY:
        return "BUY"
    if direction == Direction.SELL:
        return "SELL"
    return "HOLD"
