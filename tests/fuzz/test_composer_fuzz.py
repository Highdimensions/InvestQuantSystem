"""Fuzz tests for StrategyComposer + bindings integration."""

from __future__ import annotations

from datetime import timedelta
from random import Random

import pytest

from tests.helpers.orchestration import OrchestrationHarness, make_bar, utc


def _random_bindings(rng: Random, n: int) -> tuple:
    from quant_signal_system.backtest.run_spec import StrategyBinding

    return tuple(
        StrategyBinding(
            binding_id=f"b{i}",
            strategy_name=rng.choice(["rule_vol_breakout", "unknown_strategy"]),
            strategy_version=f"v{i}",
            parameter_hash=f"ph{i}",
            universe_id="u1",
            universe_version="v1",
            feature_version="f1",
        )
        for i in range(n)
    )


def _bars(rng: Random, n: int = 5) -> list:
    start = utc(2025, 6, 2, 9, 30)
    return [
        make_bar("300346", start + timedelta(minutes=i), close=42.0 + rng.uniform(-1, 1), volume=1000)
        for i in range(n)
    ]


class TestComposerFuzz:
    @pytest.mark.parametrize("iteration", range(10))
    def test_random_binding_count(self, iteration: int) -> None:
        rng = Random(iteration + 99)
        n = rng.randint(1, 5)
        bindings = _random_bindings(rng, n)
        harness = OrchestrationHarness(symbols=("300346",))
        from quant_signal_system.backtest.orchestrator import BacktestOrchestrator
        from quant_signal_system.backtest.run_spec import BacktestRunSpec

        spec = BacktestRunSpec(
            from_time=harness.spec_from,
            to_time=harness.spec_to,
            timeframe="1m",
            data_source_version="test-v1",
            as_of_version="asof-v1",
            strategy_bindings=bindings,
        )

        class _Repo:
            def save_bar(self, bar: object) -> None:
                return None

        from quant_signal_system.signals.repository import InMemorySignalRepository
        from quant_signal_system.signals.service import SignalService
        from quant_signal_system.time.clock import VirtualClock

        clock = VirtualClock(current_time=harness.spec_from)
        orchestrator = BacktestOrchestrator(
            spec=spec,
            universe_resolver=harness.build_universe(),
            market_repo=_Repo(),  # type: ignore[arg-type]
            signal_service=SignalService(clock=clock),
            signal_repo=InMemorySignalRepository(),
            clock=clock,
        )
        try:
            result = orchestrator.run(_bars(rng))
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"composer crashed on iteration {iteration}: {exc!r}")
        assert isinstance(result.signal_ids, tuple)
        # Each binding has its own state slot, so signal ids across runs are
        # unique by (binding_id, bar-time) — never duplicates.
        assert len(set(result.signal_ids)) == len(result.signal_ids)
