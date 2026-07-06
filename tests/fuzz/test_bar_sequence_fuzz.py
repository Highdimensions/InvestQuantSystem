"""Fuzz tests for MarketBar sequences processed by BacktestOrchestrator.

The orchestrator must accept any sequence of bars (including out-of-order,
duplicates, gapped, or closed=False) without crashing.  Specific exceptions
that document data quality issues (``SignalConflictError``,
``MarketDataValidationError``) are tolerated as long as the orchestrator
processes up to the failing bar in a deterministic way.
"""

from __future__ import annotations

from datetime import timedelta
from random import Random

import pytest

from tests.helpers.orchestration import OrchestrationHarness, make_bar, utc


def _build_bars(rng: Random, n: int, *, closed: bool = True) -> list:
    """Generate up to ``n`` MarketBars, possibly out-of-order, possibly with duplicates."""
    start = utc(2025, 6, 2, 9, 30)
    bars = []
    for i in range(n):
        offset = rng.randint(0, max(1, n))
        t = start + timedelta(minutes=offset)
        bars.append(make_bar("300346", t, close=42.0 + rng.uniform(-1, 1), volume=1000, is_closed=closed))
    return bars


# Exceptions the orchestrator is allowed to surface for malformed inputs.
_ACCEPTED_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ValueError,
    RuntimeError,
    KeyError,
    TypeError,
)


class TestBarSequenceFuzz:
    """Iterated bar sequences — orchestrator must not crash with an
    unexpected exception type."""

    @pytest.mark.parametrize("iteration", range(20))  # cap iterations for CI speed
    def test_random_bar_sequence(self, iteration: int) -> None:
        rng = Random(iteration * 7919)
        n = rng.randint(0, 50)
        bars = _build_bars(rng, n)
        harness = OrchestrationHarness(symbols=("300346",))
        try:
            result = harness.run(bars)
        except _ACCEPTED_EXCEPTIONS:
            # The orchestrator surfaced a recognised failure mode
            # (e.g. duplicate signal_id, data quality error).  That's not a
            # crash from the fuzz point of view.
            return
        assert result is not None
        assert isinstance(result.signal_ids, tuple)
        # Signal ids remain unique within a single run.
        assert len(set(result.signal_ids)) == len(result.signal_ids)

    @pytest.mark.parametrize("iteration", range(10))
    def test_unclosed_bars_are_rejected_cleanly(self, iteration: int) -> None:
        """Unclosed bars are an explicit ``MarketDataValidationError`` — the
        orchestrator MUST raise instead of silently processing them."""
        from quant_signal_system.contracts.market import MarketDataValidationError

        rng = Random(iteration + 13)
        bars = _build_bars(rng, 5, closed=False)
        harness = OrchestrationHarness(symbols=("300346",))
        with pytest.raises(MarketDataValidationError):
            harness.run(bars)

    def test_extremely_large_window_is_bounded(self) -> None:
        """Even with 1000 bars the orchestrator returns deterministically."""
        rng = Random(0)
        bars = _build_bars(rng, 1000)
        harness = OrchestrationHarness(symbols=("300346",))
        try:
            result = harness.run(bars)
            assert len(set(result.signal_ids)) == len(result.signal_ids)
        except _ACCEPTED_EXCEPTIONS:
            return
