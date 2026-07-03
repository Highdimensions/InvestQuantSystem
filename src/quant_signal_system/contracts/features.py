"""Feature and regime contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    schema_version: str
    feature_snapshot_id: str
    symbol: str
    market_data_time: datetime
    generated_at: datetime
    feature_version: str
    lookback_window: str
    features: Mapping[str, float | int | str | None]
    missing_data_flags: tuple[str, ...]
    input_bar_range: str

    def validate_visible_at(self, event_time: datetime) -> None:
        require_aware_utc(self.market_data_time, "market_data_time")
        require_aware_utc(self.generated_at, "generated_at")
        require_aware_utc(event_time, "event_time")
        if not self.schema_version or not self.feature_snapshot_id or not self.feature_version:
            raise MarketDataValidationError("feature identity and version fields are required")
        if self.generated_at > event_time:
            raise MarketDataValidationError("feature snapshot cannot be generated after event_time")
        if self.market_data_time > event_time:
            raise MarketDataValidationError("feature snapshot cannot use future market data")


@dataclass(frozen=True, slots=True)
class MarketRegime:
    schema_version: str
    symbol: str
    market_data_time: datetime
    generated_at: datetime
    regime_version: str
    regime_label: str
    confidence: float | None
    inputs: Mapping[str, str]
    as_of_version: str
    unavailable_inputs: tuple[str, ...] = ()

    def validate_visible_at(self, event_time: datetime) -> None:
        require_aware_utc(self.market_data_time, "market_data_time")
        require_aware_utc(self.generated_at, "generated_at")
        require_aware_utc(event_time, "event_time")
        if not self.schema_version or not self.regime_version or not self.as_of_version:
            raise MarketDataValidationError("regime version fields are required")
        if self.generated_at > event_time or self.market_data_time > event_time:
            raise MarketDataValidationError("market regime cannot use future data")

