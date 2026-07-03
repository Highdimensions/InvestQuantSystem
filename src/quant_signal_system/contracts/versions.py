"""Version and run metadata contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from quant_signal_system.contracts.market import require_aware_utc


class StrategyStatus(StrEnum):
    DRAFT = "DRAFT"
    SHADOW = "SHADOW"
    ACTIVE_RESEARCH = "ACTIVE_RESEARCH"
    DEPRECATED = "DEPRECATED"


@dataclass(frozen=True, slots=True)
class StrategyVersion:
    strategy_name: str
    strategy_version: str
    feature_version: str
    parameter_hash: str
    code_version: str
    created_at: datetime
    description: str
    status: StrategyStatus = StrategyStatus.DRAFT


@dataclass(frozen=True, slots=True)
class ConfigSnapshot:
    snapshot_id: str
    created_at: datetime
    versions: Mapping[str, str]
    parameter_hash: str

    def validate(self) -> None:
        require_aware_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class ReplayRun:
    replay_run_id: str
    created_at: datetime
    symbol: str
    timeframe: str
    from_time: datetime
    to_time: datetime
    data_source_version: str
    as_of_version: str
    strategy_version: str
    feature_version: str
    parameter_hash: str
    trading_calendar_version: str
    input_snapshot_hash: str


@dataclass(frozen=True, slots=True)
class ShadowRun:
    shadow_run_id: str
    created_at: datetime
    data_source_version: str
    as_of_version: str
    strategy_version: str
    feature_version: str
    parameter_hash: str
    trading_calendar_version: str

