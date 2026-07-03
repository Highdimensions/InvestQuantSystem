"""Multi-strategy scheduling and conflict aggregation.

`StrategyComposer` runs N strategies against the same closed bar and reduces
their `SignalCandidate` outputs into at most one surviving candidate. The
reduction policy is explicit so downstream consumers can audit what the
system chose when strategies disagreed.

Three policies are supported:

* ``PRIORITY_MAX_CONFIDENCE`` (default) — pick the highest-priority
  candidate; break ties by the largest `confidence`. Directional conflicts
  (BUY vs SELL) cause the composer to emit no signal and surface the
  disagreement via `reason_codes` for debugging.
* ``UNANIMOUS`` — every emitting strategy must agree on direction and
  action; conflicts produce no signal.
* ``SCORE_WEIGHTED`` — compute a weighted score sum; the final direction
  is the sign of the weighted score. Weights must be positive.

`ComposerConflictRecord` is the metadata surfaced when a conflict is
detected and the composer chooses to abstain. It is propagated via
``signal_id`` chains and audit logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Mapping, Sequence

from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.contracts.signals import (
    Direction,
    SignalCandidate,
)
from quant_signal_system.strategies.protocol import StrategyRuntime


class ConflictPolicy(StrEnum):
    PRIORITY_MAX_CONFIDENCE = "PRIORITY_MAX_CONFIDENCE"
    UNANIMOUS = "UNANIMOUS"
    SCORE_WEIGHTED = "SCORE_WEIGHTED"


class ComposerConflictError(ValueError):
    """Raised when the composer cannot reconcile the configured strategies."""


@dataclass(frozen=True, slots=True)
class ComposerConflictRecord:
    """Audit payload describing a conflict and the composer's decision."""

    market_data_time: object
    symbol: str
    policy: ConflictPolicy
    candidates: tuple[SignalCandidate, ...]
    decision: str
    reason_codes: tuple[str, ...]

    def to_mapping(self) -> Mapping[str, object]:
        return {
            "symbol": self.symbol,
            "policy": self.policy.value,
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "candidates": [
                {
                    "strategy_name": cand.strategy_name,
                    "strategy_version": cand.strategy_version,
                    "direction": int(cand.direction),
                    "score": str(cand.score),
                    "confidence": str(cand.confidence),
                    "reason_codes": list(cand.reason_codes),
                }
                for cand in self.candidates
            ],
        }


@dataclass(frozen=True, slots=True)
class StrategyComposer:
    """Aggregate multiple `StrategyRuntime` instances over one closed bar."""

    runtimes: tuple[StrategyRuntime, ...]
    weights: tuple[Decimal, ...] = field(default_factory=tuple)
    policy: ConflictPolicy = ConflictPolicy.PRIORITY_MAX_CONFIDENCE

    def __post_init__(self) -> None:
        if not self.runtimes:
            raise ComposerConflictError("StrategyComposer requires at least one runtime")
        if self.policy is ConflictPolicy.SCORE_WEIGHTED:
            if len(self.weights) != len(self.runtimes):
                raise ComposerConflictError(
                    "SCORE_WEIGHTED policy requires one weight per runtime"
                )
            if any(weight <= Decimal("0") for weight in self.weights):
                raise ComposerConflictError("SCORE_WEIGHTED weights must be positive")
        elif self.weights and len(self.weights) != len(self.runtimes):
            raise ComposerConflictError(
                "weights, when provided, must align with the runtimes tuple"
            )

    @classmethod
    def single(
        cls,
        runtime: StrategyRuntime,
        *,
        policy: ConflictPolicy = ConflictPolicy.PRIORITY_MAX_CONFIDENCE,
    ) -> "StrategyComposer":
        return cls(runtimes=(runtime,), policy=policy)

    def on_bar(
        self,
        bar: MarketBar,
        snapshot: FeatureSnapshot,
        regime: MarketRegime | None = None,
    ) -> SignalCandidate | None:
        candidates: list[SignalCandidate] = []
        for runtime in self.runtimes:
            candidate = runtime.on_bar(bar, snapshot, regime)
            if candidate is not None:
                candidates.append(candidate)

        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        if self.policy is ConflictPolicy.PRIORITY_MAX_CONFIDENCE:
            return self._resolve_priority_max_confidence(bar, candidates)
        if self.policy is ConflictPolicy.UNANIMOUS:
            return self._resolve_unanimous(bar, candidates)
        if self.policy is ConflictPolicy.SCORE_WEIGHTED:
            return self._resolve_score_weighted(bar, candidates)
        raise ComposerConflictError(f"unknown policy {self.policy!r}")

    def _resolve_priority_max_confidence(
        self,
        bar: MarketBar,
        candidates: Sequence[SignalCandidate],
    ) -> SignalCandidate | None:
        """Pick the highest-priority candidate; on ties pick the largest confidence.

        Direction conflicts are not resolvable here: BUY vs SELL must be
        surfaced as a conflict record and the composer abstains.
        """

        unique_directions = {cand.direction for cand in candidates}
        if len(unique_directions) > 1:
            self._record_conflict(
                bar=bar,
                candidates=tuple(candidates),
                policy=ConflictPolicy.PRIORITY_MAX_CONFIDENCE,
                decision="ABSTAIN_DIRECTION_CONFLICT",
            )
            return None

        ordered = sorted(
            candidates,
            key=lambda cand: (
                -self._priority_of(cand.strategy_name),
                -float(cand.confidence),
            ),
        )
        winner = ordered[0]
        aggregated = winner.reason_codes + tuple(
            f"AGGREGATED:{cand.strategy_name}" for cand in candidates if cand is not winner
        )
        return replace_candidate(winner, reason_codes=aggregated)

    def _resolve_unanimous(
        self,
        bar: MarketBar,
        candidates: Sequence[SignalCandidate],
    ) -> SignalCandidate | None:
        first = candidates[0]
        if all(
            cand.direction == first.direction
            and cand.signal_action == first.signal_action
            for cand in candidates
        ):
            aggregated = first.reason_codes + tuple(
                f"UNANIMOUS:{cand.strategy_name}" for cand in candidates if cand is not first
            )
            return replace_candidate(first, reason_codes=aggregated)
        self._record_conflict(
            bar=bar,
            candidates=tuple(candidates),
            policy=ConflictPolicy.UNANIMOUS,
            decision="ABSTAIN_UNANIMOUS_FAILED",
        )
        return None

    def _resolve_score_weighted(
        self,
        bar: MarketBar,
        candidates: Sequence[SignalCandidate],
    ) -> SignalCandidate | None:
        weights = self.weights
        weighted_score = Decimal("0")
        for cand, weight in zip(candidates, weights):
            signed = float(cand.score) * (
                1 if cand.direction == Direction.BUY else (-1 if cand.direction == Direction.SELL else 0)
            )
            weighted_score += Decimal(str(signed)) * weight

        if weighted_score == Decimal("0"):
            self._record_conflict(
                bar=bar,
                candidates=tuple(candidates),
                policy=ConflictPolicy.SCORE_WEIGHTED,
                decision="ABSTAIN_WEIGHTED_ZERO",
            )
            return None

        anchor = candidates[0]
        if weighted_score > 0:
            winner_direction = Direction.BUY
        else:
            winner_direction = Direction.SELL
        aggregated = anchor.reason_codes + (
            f"WEIGHTED_SCORE:{weighted_score:.4f}",
        )
        return replace_candidate(
            anchor,
            direction=winner_direction,
            reason_codes=aggregated,
        )

    def _priority_of(self, strategy_name: str) -> int:
        for index, runtime in enumerate(self.runtimes):
            if runtime.name == strategy_name:
                return len(self.runtimes) - index
        return 0

    def _record_conflict(
        self,
        *,
        bar: MarketBar,
        candidates: Sequence[SignalCandidate],
        policy: ConflictPolicy,
        decision: str,
    ) -> ComposerConflictRecord:
        reason_codes = (
            "CONFLICT_BUY_SELL" if {cand.direction for cand in candidates} == {Direction.BUY, Direction.SELL} else "CONFLICT",
        )
        record = ComposerConflictRecord(
            market_data_time=bar.market_data_time,
            symbol=bar.symbol,
            policy=policy,
            candidates=tuple(candidates),
            decision=decision,
            reason_codes=reason_codes + (decision,),
        )
        return record


def replace_candidate(
    candidate: SignalCandidate,
    *,
    reason_codes: tuple[str, ...] | None = None,
    direction: Direction | None = None,
) -> SignalCandidate:
    """Construct a copy of `candidate` with selected fields overridden."""

    from dataclasses import replace

    updates: dict[str, object] = {}
    if reason_codes is not None:
        updates["reason_codes"] = reason_codes
    if direction is not None:
        updates["direction"] = direction
    if not updates:
        return candidate
    return replace(candidate, **updates)


def describe_composer(composer: StrategyComposer) -> str:
    names = ",".join(runtime.name for runtime in composer.runtimes)
    return f"{composer.policy.value}[{names}]"


__all__ = [
    "ComposerConflictError",
    "ComposerConflictRecord",
    "ConflictPolicy",
    "StrategyComposer",
    "describe_composer",
    "replace_candidate",
]