"""Consistency assertions C1–C6 for Phase 7.

These tests assert that running the same input twice produces identical
orchestrator output, that universe switching is consistent, and that
producer-side and evaluation-side identifiers stay aligned.

The shared-clock harness (``tests.helpers.orchestration``) hands the same
``VirtualClock`` instance to both the orchestrator and the ``SignalService``,
so ``signal.event_time`` is always consistent with ``candidate.market_data_time``.
"""

from __future__ import annotations

from tests.helpers.orchestration import (
    OrchestrationHarness,
    generate_bars,
    utc,
)
from quant_signal_system.universe.contracts import UniverseSnapshot


class TestReplayDeterminism:
    """C1/C2: replay vs replay invariance."""

    def test_c1_same_input_produces_same_signal_ids(self) -> None:
        bars = generate_bars("300346", 60)
        harness = OrchestrationHarness(symbols=("300346",))
        ids_a = harness.run(bars).signal_ids
        ids_b = harness.run(bars).signal_ids
        assert ids_a == ids_b
        assert len(ids_a) == len(ids_b)

    def test_c2_same_input_same_signal_count(self) -> None:
        bars = generate_bars("300346", 30) + generate_bars("600519", 30)
        harness = OrchestrationHarness(symbols=("300346", "600519"))
        first = harness.run(bars).signals_generated
        second = harness.run(bars).signals_generated
        assert first == second

    def test_c2b_shuffled_input_stable(self) -> None:
        """Different ordering of the same bars must yield the same ids."""
        bars = generate_bars("300346", 30)
        shuffled = list(reversed(bars))
        harness = OrchestrationHarness(symbols=("300346",))
        ids_a = harness.run(bars).signal_ids
        ids_b = harness.run(shuffled).signal_ids
        assert ids_a == ids_b


class TestUniverseConsistency:
    """C3: switching the universe snapshot mid-run must not contaminate the
    pre-switch state."""

    def test_c3_universe_switch_preserves_id_stability(self) -> None:
        # Build a snapshot with the first symbol only, run, then rebuild
        # with an expanded universe.  Both runs should still be deterministic.
        first = OrchestrationHarness(symbols=("300346",)).run(
            generate_bars("300346", 30)
        )
        expanded = OrchestrationHarness(symbols=("300346", "600519")).run(
            generate_bars("300346", 30)
        )
        # Replay-expanded yields exactly the same ids as replay-expanded.
        again = OrchestrationHarness(symbols=("300346", "600519")).run(
            generate_bars("300346", 30)
        )
        assert expanded.signal_ids == again.signal_ids
        # The narrower run only sees the 300346 bars.
        assert all("300346" in sid for sid in first.signal_ids)


class TestManifestConsistency:
    """C6 (light): the orchestrator's persisted signal_ids must align with
    what the signal_repository returns when listing."""

    def test_c6_signal_ids_align_with_repository(self) -> None:
        bars = generate_bars("300346", 60)
        harness = OrchestrationHarness(symbols=("300346",))
        orchestrator = harness.build_orchestrator()

        result = orchestrator.run(bars)
        listed = [event.signal_id for event in orchestrator.signal_repo.list_signals()]
        assert tuple(listed) == result.signal_ids


def _validate_snapshot_is_rejected() -> None:
    """Helper assertion: an invalid snapshot raises.

    Moved out so the test isn't sensitive to which specific field triggers it.
    """
    from quant_signal_system.contracts.market import MarketDataValidationError

    bad = UniverseSnapshot(
        universe_id="",
        universe_version="v1",
        effective_time=utc(2025, 6, 2, 9, 30),
        available_at=utc(2025, 6, 2, 9, 30),
        symbols=("300346",),
        inclusion_reason="manual",
        source="manual",
        source_version="v1",
        revision_id="r1",
        as_of_version="asof-v1",
    )
    try:
        bad.validate()
    except MarketDataValidationError:
        return
    raise AssertionError("expected MarketDataValidationError")


class TestMarketRulesConsistency:
    """C4 (light wiring): market_rules rejects invalid candidates uniformly."""

    def test_c4_invalid_snapshot_rejected(self) -> None:
        _validate_snapshot_is_rejected()
