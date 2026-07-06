"""Fuzz tests for UniverseSnapshot validation."""

from __future__ import annotations

from datetime import timedelta
from random import Random

import pytest

from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.universe.contracts import UniverseSnapshot


def _build_snapshot(rng: Random, *, mutate: int) -> UniverseSnapshot:
    start = UniverseSnapshot(
        universe_id="u1",
        universe_version="v1",
        effective_time=__import__("datetime").datetime(2025, 6, 2, 9, 30, tzinfo=__import__("datetime").timezone.utc),
        available_at=__import__("datetime").datetime(2025, 6, 2, 9, 30, tzinfo=__import__("datetime").timezone.utc),
        symbols=("300346", "600519"),
        inclusion_reason="manual",
        source="manual",
        source_version="v1",
        revision_id="r1",
        as_of_version="asof-v1",
    )
    fields = (
        "universe_id",
        "universe_version",
        "effective_time",
        "available_at",
        "symbols",
        "inclusion_reason",
        "source",
        "source_version",
        "revision_id",
        "as_of_version",
    )
    for _ in range(mutate):
        choice = rng.choice(fields)
        if choice in {"universe_id", "universe_version", "inclusion_reason", "source", "source_version", "revision_id", "as_of_version"}:
            object.__setattr__(start, choice, "")
        elif choice == "effective_time":
            new_eff = start.effective_time + timedelta(minutes=rng.randint(-10, 10))
            object.__setattr__(start, "effective_time", new_eff)
        elif choice == "available_at":
            new_avail = start.available_at + timedelta(minutes=rng.randint(-10, 10))
            object.__setattr__(start, "available_at", new_avail)
        elif choice == "symbols":
            object.__setattr__(start, "symbols", ())
    return start


class TestUniverseFuzz:
    @pytest.mark.parametrize("iteration", range(20))
    def test_random_mutations_either_validate_or_raise(self, iteration: int) -> None:
        rng = Random(iteration + 7)
        snap = _build_snapshot(rng, mutate=2)
        try:
            snap.validate()
        except MarketDataValidationError:
            return
        # If it validates, the snapshot must have non-empty identity.
        assert snap.universe_id
        assert snap.universe_version
        assert snap.symbols
        assert snap.source_version
        assert snap.revision_id
        assert snap.as_of_version
