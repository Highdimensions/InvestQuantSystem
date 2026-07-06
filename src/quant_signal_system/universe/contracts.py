"""Universe snapshot contracts for versioned stock pool management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from quant_signal_system.contracts.market import (
    MarketDataValidationError,
    require_aware_utc,
)


@dataclass(frozen=True, slots=True)
class UniverseSnapshot:
    """A versioned snapshot of a stock pool visible at a given effective time.

    A UniverseSnapshot prevents the backtest engine from using future index
    constituents or sector classifications that were not yet published.
    """

    # Identity
    universe_id: str
    universe_version: str

    # Time semantics
    effective_time: datetime     # When this constituent set takes effect
    available_at: datetime       # When this snapshot becomes visible to the system

    # Content
    symbols: tuple[str, ...]
    inclusion_reason: str       # "index_constituent" | "sector_classification" | "manual"
    source: str                  # "CSI" | "SSE" | "SZSE" | "wind" | "manual"
    source_version: str

    # Revision tracking
    revision_id: str
    as_of_version: str

    # Optional / with defaults
    schema_version: str = "universe-snapshot-v1"
    replaced_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""

    def validate(self) -> None:
        """Validate time semantics and identity fields."""
        require_aware_utc(self.effective_time, "effective_time")
        require_aware_utc(self.available_at, "available_at")

        if not self.universe_id or not self.universe_id.strip():
            raise MarketDataValidationError("universe_id is required")
        if not self.universe_version or not self.universe_version.strip():
            raise MarketDataValidationError("universe_version is required")
        if not self.symbols:
            raise MarketDataValidationError("symbols must not be empty")
        if self.available_at > self.effective_time:
            raise MarketDataValidationError(
                "available_at must not be after effective_time"
            )
        if not self.source_version or not self.source_version.strip():
            raise MarketDataValidationError("source_version is required")
        if not self.revision_id or not self.revision_id.strip():
            raise MarketDataValidationError("revision_id is required")
        if not self.as_of_version or not self.as_of_version.strip():
            raise MarketDataValidationError("as_of_version is required")

    def is_visible_at(self, decision_time: datetime) -> bool:
        """Return True if this snapshot is visible at decision_time."""
        require_aware_utc(decision_time, "decision_time")
        return self.available_at <= decision_time

    def universe_hash(self) -> str:
        """Deterministic hash of the snapshot identity for equality checks."""
        import hashlib

        symbols_key = ",".join(sorted(self.symbols))
        raw = f"{self.universe_id}|{self.universe_version}|{self.effective_time.isoformat()}|{self.available_at.isoformat()}|{symbols_key}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
