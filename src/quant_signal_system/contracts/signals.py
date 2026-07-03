"""Signal contracts and A-share-safe signal semantics."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum

from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc


class Direction(IntEnum):
    SELL = -1
    HOLD = 0
    BUY = 1


class SignalAction(StrEnum):
    BUY = "BUY"
    REDUCE_LONG = "REDUCE_LONG"
    CLEAR_LONG = "CLEAR_LONG"
    RISK_AVOID = "RISK_AVOID"
    HOLD = "HOLD"


class ExposureEffect(StrEnum):
    INCREASE_LONG = "INCREASE_LONG"
    DECREASE_LONG = "DECREASE_LONG"
    FLAT = "FLAT"
    NO_ACTION = "NO_ACTION"


class ExecutionStatus(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    UNEXECUTABLE = "UNEXECUTABLE"
    UNKNOWN_AT_EVENT_TIME = "UNKNOWN_AT_EVENT_TIME"


@dataclass(frozen=True, slots=True)
class SignalCandidate:
    symbol: str
    direction: Direction
    signal_action: SignalAction
    exposure_effect: ExposureEffect
    market_data_time: datetime
    reference_price: Decimal
    score: Decimal
    confidence: Decimal
    horizon_seconds: int
    reason_codes: tuple[str, ...]
    invalid_condition: str | None
    feature_snapshot: FeatureSnapshot
    market_regime: MarketRegime | None
    strategy_name: str
    strategy_version: str
    feature_version: str
    code_version: str
    parameter_hash: str
    data_source_version: str
    as_of_version: str

    def validate(self) -> None:
        require_aware_utc(self.market_data_time, "market_data_time")
        if self.reference_price <= 0:
            raise MarketDataValidationError("reference_price must be positive")
        if self.horizon_seconds <= 0:
            raise MarketDataValidationError("horizon_seconds must be positive")
        if self.direction == Direction.SELL and self.signal_action == SignalAction.BUY:
            raise MarketDataValidationError("A-share Sell signal cannot map to BUY action")
        if self.direction == Direction.SELL and self.exposure_effect == ExposureEffect.INCREASE_LONG:
            raise MarketDataValidationError("A-share Sell signal cannot increase long exposure")


@dataclass(frozen=True, slots=True)
class SignalEvent:
    schema_version: str
    signal_id: str
    symbol: str
    direction: Direction
    signal_action: SignalAction
    exposure_effect: ExposureEffect
    event_time: datetime
    market_data_time: datetime
    ingest_time: datetime
    executable_time: datetime
    reference_price: Decimal
    executable_price: Decimal | None
    executable_price_source: str | None
    execution_status: ExecutionStatus
    unexecutable_reason: str | None
    score: Decimal
    confidence: Decimal
    horizon_seconds: int
    reason_codes: tuple[str, ...]
    invalid_condition: str | None
    feature_snapshot: FeatureSnapshot
    market_regime: MarketRegime | None
    strategy_name: str
    strategy_version: str
    feature_version: str
    code_version: str
    parameter_hash: str
    data_source_version: str
    as_of_version: str
    created_at: datetime

    def validate(self) -> None:
        for field_name in (
            "event_time",
            "market_data_time",
            "ingest_time",
            "executable_time",
            "created_at",
        ):
            require_aware_utc(getattr(self, field_name), field_name)
        if self.market_data_time > self.event_time:
            raise MarketDataValidationError("event_time cannot be before market_data_time")
        if self.executable_time <= self.event_time:
            raise MarketDataValidationError("executable_time must be after event_time")
        if self.reference_price <= 0:
            raise MarketDataValidationError("reference_price must be positive")
        if self.executable_price is not None and self.executable_price <= 0:
            raise MarketDataValidationError("executable_price must be positive")
        if self.direction == Direction.SELL and self.exposure_effect == ExposureEffect.INCREASE_LONG:
            raise MarketDataValidationError("A-share Sell signal cannot increase long exposure")
        self.feature_snapshot.validate_visible_at(self.event_time)
        if self.market_regime is not None:
            self.market_regime.validate_visible_at(self.event_time)


def deterministic_signal_id(candidate: SignalCandidate, *, event_time: datetime) -> str:
    payload = {
        "symbol": candidate.symbol,
        "direction": int(candidate.direction),
        "market_data_time": candidate.market_data_time.isoformat(),
        "event_time": event_time.isoformat(),
        "strategy_name": candidate.strategy_name,
        "strategy_version": candidate.strategy_version,
        "feature_version": candidate.feature_version,
        "parameter_hash": candidate.parameter_hash,
        "data_source_version": candidate.data_source_version,
        "as_of_version": candidate.as_of_version,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:32]

