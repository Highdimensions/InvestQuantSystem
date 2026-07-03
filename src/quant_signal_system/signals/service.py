"""Create immutable SignalEvent objects from strategy candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from quant_signal_system.config.versions import VersionRegistry
from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.contracts.signals import (
    ExecutionStatus,
    SignalCandidate,
    SignalEvent,
    deterministic_signal_id,
)
from quant_signal_system.time.clock import Clock


@dataclass(frozen=True, slots=True)
class SignalService:
    clock: Clock
    schema_version: str = "signal-event-v1"
    version_registry: VersionRegistry | None = None

    def create_event(self, candidate: SignalCandidate) -> SignalEvent:
        candidate.validate()
        self._verify_strategy_frozen(candidate)
        event_time = self.clock.now()
        executable_time = event_time + timedelta(seconds=1)
        signal = SignalEvent(
            schema_version=self.schema_version,
            signal_id=deterministic_signal_id(candidate, event_time=event_time),
            symbol=candidate.symbol,
            direction=candidate.direction,
            signal_action=candidate.signal_action,
            exposure_effect=candidate.exposure_effect,
            event_time=event_time,
            market_data_time=candidate.market_data_time,
            ingest_time=event_time,
            executable_time=executable_time,
            reference_price=candidate.reference_price,
            executable_price=None,
            executable_price_source="NEXT_AVAILABLE_BAR",
            execution_status=ExecutionStatus.UNKNOWN_AT_EVENT_TIME,
            unexecutable_reason=None,
            score=candidate.score,
            confidence=candidate.confidence,
            horizon_seconds=candidate.horizon_seconds,
            reason_codes=candidate.reason_codes,
            invalid_condition=candidate.invalid_condition,
            feature_snapshot=candidate.feature_snapshot,
            market_regime=candidate.market_regime,
            strategy_name=candidate.strategy_name,
            strategy_version=candidate.strategy_version,
            feature_version=candidate.feature_version,
            code_version=candidate.code_version,
            parameter_hash=candidate.parameter_hash,
            data_source_version=candidate.data_source_version,
            as_of_version=candidate.as_of_version,
            created_at=event_time,
        )
        signal.validate()
        return signal

    def _verify_strategy_frozen(self, candidate: SignalCandidate) -> None:
        if self.version_registry is None:
            return
        if not self.version_registry.is_strategy_frozen(
            strategy_name=candidate.strategy_name,
            strategy_version=candidate.strategy_version,
            parameter_hash=candidate.parameter_hash,
            code_version=candidate.code_version,
        ):
            raise MarketDataValidationError(
                "strategy identity is not frozen: "
                f"name={candidate.strategy_name!r} "
                f"version={candidate.strategy_version!r} "
                f"parameter_hash={candidate.parameter_hash!r} "
                f"code_version={candidate.code_version!r}"
            )