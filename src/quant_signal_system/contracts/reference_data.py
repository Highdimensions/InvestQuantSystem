"""As-of reference data contracts used to prevent future revision leakage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc


@dataclass(frozen=True, slots=True)
class AsOfDataset:
    schema_version: str
    dataset: str
    key: str
    effective_time: datetime
    available_at: datetime
    revision_id: str
    as_of_version: str
    payload: Mapping[str, object]

    def validate_visible_at(self, decision_time: datetime) -> None:
        require_aware_utc(self.effective_time, "effective_time")
        require_aware_utc(self.available_at, "available_at")
        require_aware_utc(decision_time, "decision_time")

        if not self.schema_version or not self.dataset or not self.key:
            raise MarketDataValidationError("as-of dataset identity fields are required")
        if not self.revision_id or not self.as_of_version:
            raise MarketDataValidationError("revision_id and as_of_version are required")
        if self.available_at > decision_time:
            raise MarketDataValidationError("reference data is not visible at decision_time")
        if self.available_at.utcoffset() != timezone.utc.utcoffset(self.available_at):
            raise MarketDataValidationError("available_at must be stored in UTC")

