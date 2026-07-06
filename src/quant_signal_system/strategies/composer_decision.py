"""ComposerDecision: immutable audit record of a multi-strategy conflict resolution.

Phase 3 deliverable.  Each ComposerDecision captures:
- The policy applied
- All participating candidates
- The winning candidate(s) (if any)
- Whether the composer abstained and why
- Rejected candidates and their reasons

Persistence is append-only and idempotent: writing the same decision twice
returns the existing record without raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from quant_signal_system.contracts.signals import SignalCandidate
from quant_signal_system.strategies.composer import ConflictPolicy

if TYPE_CHECKING:
    pass


def _composer_decision_id(
    binding_id: str,
    market_data_time: datetime,
    symbol: str,
    policy: ConflictPolicy,
) -> str:
    """Deterministic decision_id from binding + time + symbol + policy."""
    import hashlib

    raw = f"{binding_id}|{market_data_time.isoformat()}|{symbol}|{policy.value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ComposerDecision:
    """Immutable audit record of a multi-strategy conflict resolution."""

    schema_version: str = "composer-decision-v1"
    decision_id: str = ""
    binding_id: str = ""
    market_data_time: datetime = field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    symbol: str = ""
    policy: ConflictPolicy = ConflictPolicy.PRIORITY_MAX_CONFIDENCE
    winning_candidates: tuple[SignalCandidate, ...] = field(default_factory=tuple)
    abstained: bool = False
    abstention_reason: str | None = None
    rejected_candidates: tuple[SignalCandidate, ...] = field(default_factory=tuple)
    rejection_reasons: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(
        default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc)
    )

    def __post_init__(self) -> None:
        if not self.decision_id:
            raise ValueError("decision_id is required")
        if not self.binding_id:
            raise ValueError("binding_id is required")


class ComposerDecisionRepository:
    """Append-only, idempotent in-memory store for ComposerDecision.

    Writing the same decision twice (same decision_id) returns the existing
    record without raising.  Writing a decision with the same decision_id but
    different content raises ComposerDecisionConflictError.
    """

    def __init__(self) -> None:
        self._records: dict[str, ComposerDecision] = {}

    def append(self, decision: ComposerDecision) -> ComposerDecision:
        """Append a decision idempotently.

        Returns the stored decision (either the newly appended one or the
        pre-existing one with the same decision_id).
        """
        existing = self._records.get(decision.decision_id)
        if existing is not None:
            if existing != decision:
                raise ComposerDecisionConflictError(
                    f"ComposerDecision conflict for {decision.decision_id!r}: "
                    "same decision_id with different content"
                )
            return existing
        self._records[decision.decision_id] = decision
        return decision

    def get(self, decision_id: str) -> ComposerDecision | None:
        """Return a decision by ID, or None."""
        return self._records.get(decision_id)

    def list_for_binding(self, binding_id: str) -> tuple[ComposerDecision, ...]:
        """Return all decisions for a binding, sorted by market_data_time."""
        return tuple(
            sorted(
                (d for d in self._records.values() if d.binding_id == binding_id),
                key=lambda d: d.market_data_time,
            )
        )

    def list_for_symbol(self, symbol: str) -> tuple[ComposerDecision, ...]:
        """Return all decisions for a symbol, sorted by market_data_time."""
        return tuple(
            sorted(
                (d for d in self._records.values() if d.symbol == symbol),
                key=lambda d: d.market_data_time,
            )
        )

    def all_decisions(self) -> tuple[ComposerDecision, ...]:
        """Return all decisions, sorted by market_data_time."""
        return tuple(
            sorted(self._records.values(), key=lambda d: d.market_data_time)
        )

    def __len__(self) -> int:
        return len(self._records)


class ComposerDecisionConflictError(ValueError):
    """Raised when an append would overwrite an existing decision with different content."""
    pass
