"""Backtest run result: immutable snapshot of a completed run."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from quant_signal_system.backtest.manifest import RunWarning


@dataclass(frozen=True, slots=True)
class UniverseChangeEvent:
    """Records a universe constituent change during a backtest run."""

    universe_id: str = ""
    previous_version: str = ""
    new_version: str = ""
    effective_time: datetime = field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc), kw_only=True
    )
    schema_version: str = field(default="universe-change-v1", kw_only=True)
    change_count: int = field(default=0, kw_only=True)


@dataclass(frozen=True, slots=True)
class BacktestRunResult:
    """Immutable snapshot of a completed backtest run for Phase 2.

    Phase 2 result contains only signal-layer facts.  Portfolio and evaluation
    results are added in Phase 4 and Phase 5.
    """

    # Required identity
    run_id: str = ""
    spec_hash: str = ""

    # Counts
    total_bars: int = field(default=0, kw_only=True)
    bars_skipped: int = field(default=0, kw_only=True)
    signals_generated: int = field(default=0, kw_only=True)
    signals_rejected: int = field(default=0, kw_only=True)
    out_of_order_bars: int = field(default=0, kw_only=True)
    universe_changes: int = field(default=0, kw_only=True)

    # Symbol-level counts
    bars_by_symbol: tuple[tuple[str, int], ...] = field(default_factory=tuple, kw_only=True)

    # Signal IDs (append-only)
    signal_ids: tuple[str, ...] = field(default_factory=tuple, kw_only=True)

    # Events
    universe_change_events: tuple[UniverseChangeEvent, ...] = field(default_factory=tuple, kw_only=True)
    warnings: tuple[RunWarning, ...] = field(default_factory=tuple, kw_only=True)

    # Lifecycle
    started_at: datetime = field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc), kw_only=True
    )
    finished_at: datetime = field(
        default_factory=lambda: datetime(2100, 1, 1, tzinfo=timezone.utc), kw_only=True
    )

    # Schema
    schema_version: str = field(default="backtest-run-result-v1", kw_only=True)

    def duration_seconds(self) -> float:
        """Return the run duration in seconds."""
        delta = self.finished_at - self.started_at
        return delta.total_seconds()
