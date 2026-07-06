"""State isolation per (binding_id, symbol) for multi-strategy multi-symbol backtests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from quant_signal_system.backtest.run_spec import StrategyBinding
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.strategies.protocol import StrategyRuntime
from quant_signal_system.strategies.runtime import RuleStrategyRuntime

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Helper factories (defined BEFORE classes that reference them as defaults)
# ---------------------------------------------------------------------------


def _default_feature_engine() -> RollingFeatureEngine:
    return RollingFeatureEngine(lookback=3)


def _create_runtime(binding: StrategyBinding) -> StrategyRuntime:
    return RuleStrategyRuntime(
        strategy_name=binding.strategy_name,
        strategy_version=binding.strategy_version,
        parameter_hash=binding.parameter_hash,
        code_version="research-code-v1",
        horizon_seconds=900,
    )


# ---------------------------------------------------------------------------
# StrategyBindingState
# ---------------------------------------------------------------------------


@dataclass
class StrategyBindingState:
    """Isolated runtime state for one (binding_id, symbol) pair.

    Each StrategyBindingState owns:
    - A dedicated RollingFeatureEngine instance (no shared feature state).
    - A dedicated StrategyRuntime instance (no shared strategy state).

    The instances are created lazily on first access.
    """

    binding_id: str
    symbol: str
    feature_engine: RollingFeatureEngine = field(default_factory=_default_feature_engine)
    strategy_runtime: StrategyRuntime | None = field(default=None)
    bars_received: int = 0

    def ensure_runtime(self, binding: StrategyBinding) -> StrategyRuntime:
        """Lazily create and return the StrategyRuntime for this state slot."""
        if self.strategy_runtime is None:
            self.strategy_runtime = _create_runtime(binding)
        return self.strategy_runtime


# ---------------------------------------------------------------------------
# StatePartition
# ---------------------------------------------------------------------------


@dataclass
class StatePartition:
    """Manages isolated state slots for all (binding_id, symbol) pairs.

    The partition guarantees that no feature or strategy state is shared across
    different symbols or different bindings.
    """

    _slots: dict[tuple[str, str], StrategyBindingState] = field(default_factory=dict)

    def get_or_create(
        self,
        binding_id: str,
        symbol: str,
    ) -> StrategyBindingState:
        """Return the state slot for (binding_id, symbol), creating it if needed."""
        key = (binding_id, symbol)
        if key not in self._slots:
            self._slots[key] = StrategyBindingState(binding_id=binding_id, symbol=symbol)
        return self._slots[key]

    def get(self, binding_id: str, symbol: str) -> StrategyBindingState | None:
        """Return the state slot if it exists, or None."""
        return self._slots.get((binding_id, symbol))

    def all_symbols_for(self, binding_id: str) -> frozenset[str]:
        """Return the set of all symbols that have a state slot for this binding."""
        return frozenset(sym for (bid, sym) in self._slots if bid == binding_id)

    def slot_count(self) -> int:
        """Return the total number of active state slots."""
        return len(self._slots)

    def contains(self, binding_id: str, symbol: str) -> bool:
        """Return True if a state slot exists for (binding_id, symbol)."""
        return (binding_id, symbol) in self._slots
