"""Tests for backtest/state_partition.py."""

from __future__ import annotations

from quant_signal_system.backtest.run_spec import StrategyBinding
from quant_signal_system.backtest.state_partition import StatePartition, StrategyBindingState
from quant_signal_system.strategies.runtime import RuleStrategyRuntime


def _binding(
    binding_id: str = "b1",
    strategy_name: str = "test",
    strategy_version: str = "v1",
) -> StrategyBinding:
    return StrategyBinding(
        binding_id=binding_id,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        parameter_hash="h",
        universe_id="u1",
        universe_version="v1",
        feature_version="f1",
    )


class TestStrategyBindingState:
    def test_initial_state(self) -> None:
        state = StrategyBindingState(binding_id="b1", symbol="300346")
        assert state.binding_id == "b1"
        assert state.symbol == "300346"
        assert state.bars_received == 0
        assert state.strategy_runtime is None

    def test_ensure_runtime_creates_runtime(self) -> None:
        state = StrategyBindingState(binding_id="b1", symbol="300346")
        binding = _binding()
        runtime = state.ensure_runtime(binding)
        assert isinstance(runtime, RuleStrategyRuntime)
        assert runtime.strategy_name == "test"

    def test_ensure_runtime_idempotent(self) -> None:
        state = StrategyBindingState(binding_id="b1", symbol="300346")
        binding = _binding()
        r1 = state.ensure_runtime(binding)
        r2 = state.ensure_runtime(binding)
        assert r1 is r2  # same instance


class TestStatePartition:
    def test_get_or_create(self) -> None:
        partition = StatePartition()
        state1 = partition.get_or_create("b1", "300346")
        state2 = partition.get_or_create("b1", "300346")
        assert state1 is state2  # same slot

    def test_get_or_create_different_symbols(self) -> None:
        partition = StatePartition()
        s1 = partition.get_or_create("b1", "300346")
        s2 = partition.get_or_create("b1", "600519")
        assert s1 is not s2

    def test_get_or_create_different_bindings(self) -> None:
        partition = StatePartition()
        s1 = partition.get_or_create("b1", "300346")
        s2 = partition.get_or_create("b2", "300346")
        assert s1 is not s2

    def test_get_returns_none_for_missing(self) -> None:
        partition = StatePartition()
        assert partition.get("b1", "300346") is None

    def test_get_returns_slot_when_exists(self) -> None:
        partition = StatePartition()
        expected = partition.get_or_create("b1", "300346")
        assert partition.get("b1", "300346") is expected

    def test_all_symbols_for(self) -> None:
        partition = StatePartition()
        partition.get_or_create("b1", "300346")
        partition.get_or_create("b1", "600519")
        partition.get_or_create("b2", "300346")
        symbols = partition.all_symbols_for("b1")
        assert symbols == frozenset(["300346", "600519"])

    def test_all_symbols_for_no_bindings(self) -> None:
        partition = StatePartition()
        assert partition.all_symbols_for("b1") == frozenset()

    def test_slot_count(self) -> None:
        partition = StatePartition()
        partition.get_or_create("b1", "300346")
        partition.get_or_create("b1", "600519")
        partition.get_or_create("b2", "300346")
        assert partition.slot_count() == 3

    def test_contains(self) -> None:
        partition = StatePartition()
        partition.get_or_create("b1", "300346")
        assert partition.contains("b1", "300346")
        assert not partition.contains("b1", "600519")
        assert not partition.contains("b2", "300346")

    def test_isolation_between_slots(self) -> None:
        """Verify two slots do not share feature engine or strategy runtime."""
        partition = StatePartition()
        s1 = partition.get_or_create("b1", "300346")
        s2 = partition.get_or_create("b1", "600519")

        # Ensure runtimes are created
        binding = _binding()
        r1 = s1.ensure_runtime(binding)
        r2 = s2.ensure_runtime(binding)

        # Different runtime instances
        assert r1 is not r2

        # Feature engines are separate instances
        assert s1.feature_engine is not s2.feature_engine

        # Different bars dicts
        assert s1.feature_engine is not s2.feature_engine

    def test_strategy_runtime_has_correct_identity(self) -> None:
        partition = StatePartition()
        binding = _binding(
            binding_id="vol_breakout_hs300_v1",
            strategy_name="volume_breakout",
            strategy_version="v1",
        )
        state = partition.get_or_create("vol_breakout_hs300_v1", "300346")
        runtime = state.ensure_runtime(binding)
        assert runtime.strategy_name == "volume_breakout"
        assert runtime.strategy_version == "v1"
        assert runtime.parameter_hash == "h"
