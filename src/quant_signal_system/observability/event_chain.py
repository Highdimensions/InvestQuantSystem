"""Event chain export for backtest debugging.

Implements the event type catalog from
``docs/architecture/backtest-observability.md`` Section 4.1. Each entry captures
a single logical step in the bar-to-signal pipeline with enough context for
post-hoc reconstruction of the full event timeline.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

# Event type constants matching backtest-observability.md §4.1
EVENT_TYPE_MARKET_BAR_CLOSED = "MarketBarClosed"
EVENT_TYPE_FEATURE_SNAPSHOT = "FeatureSnapshot"
EVENT_TYPE_SIGNAL_CANDIDATE = "SignalCandidate"
EVENT_TYPE_COMPOSER_DECISION = "ComposerDecision"
EVENT_TYPE_SIGNAL_EVENT = "SignalEvent"
EVENT_TYPE_ORDER_INTENT = "OrderIntent"
EVENT_TYPE_PAPER_FILL = "PaperFill"
EVENT_TYPE_EVALUATION_TASK = "EvaluationTask"

# Valid event types as a literal for type checking
_EVENT_TYPES: frozenset[str] = frozenset(
    {
        EVENT_TYPE_MARKET_BAR_CLOSED,
        EVENT_TYPE_FEATURE_SNAPSHOT,
        EVENT_TYPE_SIGNAL_CANDIDATE,
        EVENT_TYPE_COMPOSER_DECISION,
        EVENT_TYPE_SIGNAL_EVENT,
        EVENT_TYPE_ORDER_INTENT,
        EVENT_TYPE_PAPER_FILL,
        EVENT_TYPE_EVALUATION_TASK,
    }
)


@dataclass(frozen=True, slots=True)
class EventChainEntry:
    """A single timestamped event in the backtest pipeline."""

    schema_version: str = "event-chain-entry-v1"
    run_id: str = ""
    binding_id: str | None = None
    symbol: str | None = None
    event_sequence: int = 0
    event_type: str = ""
    market_data_time: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.event_type not in _EVENT_TYPES:
            raise ValueError(f"Unknown event_type: {self.event_type!r}")

    def to_dict(self) -> dict[str, Any]:
        def _serialize(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, (tuple, list)):
                return [_serialize(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj
        raw = asdict(self)
        return _serialize(raw)


class EventChainExporter:
    """Collects and writes :class:`EventChainEntry` objects to a JSONL file.

    The exporter is a no-op when ``enabled=False``. When enabled, entries are
    buffered in memory and flushed to disk on ``close()`` or when the internal
    buffer reaches ``flush_every`` entries (default 100). This prevents excessive
    I/O during backtests while ensuring that runs terminated by crashes still
    have a partial event chain on disk.
    """

    def __init__(
        self,
        output_path: Path | None = None,
        enabled: bool = True,
        flush_every: int = 100,
    ) -> None:
        self._output_path = output_path
        self._enabled = enabled
        self._flush_every = flush_every
        self._buffer: list[EventChainEntry] = []
        self._sequence: int = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def emit(
        self,
        event_type: str,
        run_id: str = "",
        *,
        binding_id: str | None = None,
        symbol: str | None = None,
        market_data_time: datetime | None = None,
        payload: dict[str, Any] | None = None,
    ) -> EventChainEntry:
        """Create and (if enabled) append one event entry.

        The entry is always returned so callers can store references for later
        linking (e.g. linking a ``SignalEvent`` back to the ``SignalCandidate``
        that generated it).
        """
        self._sequence += 1
        entry = EventChainEntry(
            run_id=run_id,
            binding_id=binding_id,
            symbol=symbol,
            event_sequence=self._sequence,
            event_type=event_type,
            market_data_time=market_data_time or datetime.now(timezone.utc),
            payload=payload or {},
        )
        if self._enabled:
            self._buffer.append(entry)
            if len(self._buffer) >= self._flush_every:
                self._flush()
        return entry

    def _flush(self) -> None:
        if not self._buffer:
            return
        if self._output_path is not None:
            self._output_path.parent.mkdir(parents=True, exist_ok=True)
            with self._output_path.open("a", encoding="utf-8") as fh:
                for entry in self._buffer:
                    fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._buffer.clear()

    def flush(self) -> None:
        """Force flush any buffered entries to disk."""
        self._flush()

    def close(self) -> None:
        """Flush and release resources."""
        self._flush()

    def entries(self) -> list[EventChainEntry]:
        """Return all buffered entries (for testing)."""
        return list(self._buffer)
