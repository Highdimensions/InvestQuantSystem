"""Historical replay runner that drives shared feature and strategy logic.

The runner is intentionally agnostic to the specific strategy implementation
and accepts either:

* a single `StrategyRuntime` (legacy single-strategy mode, preserved for
  backward compatibility), or
* a `StrategyComposer` (multi-strategy scheduling with conflict resolution).

Both shapes are normalised internally to a composer; the runner then drives
the closed-bar feature engine and the candidate pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies.composer import StrategyComposer
from quant_signal_system.strategies.protocol import StrategyRuntime
from quant_signal_system.strategies.runtime import RuleStrategyRuntime


@dataclass(frozen=True, slots=True)
class BacktestResult:
    bars_seen: int
    signals_created: int
    signal_ids: tuple[str, ...]


def _coerce_composer(value: Union[StrategyRuntime, StrategyComposer]) -> StrategyComposer:
    if isinstance(value, StrategyComposer):
        return value
    if isinstance(value, StrategyRuntime):
        return StrategyComposer.single(value)
    raise TypeError(
        "strategy_runtime must be a StrategyRuntime or StrategyComposer"
    )


@dataclass(frozen=True, slots=True)
class BacktestRunner:
    feature_engine: RollingFeatureEngine
    strategy_runtime: Union[StrategyRuntime, StrategyComposer]
    signal_service: SignalService
    signal_repository: InMemorySignalRepository
    composer: StrategyComposer = field(init=False)

    def __post_init__(self) -> None:
        composer = _coerce_composer(self.strategy_runtime)
        object.__setattr__(self, "composer", composer)

    def run_bars(self, bars: list[MarketBar]) -> BacktestResult:
        signal_ids: list[str] = []
        for bar in sorted(bars, key=lambda item: item.market_data_time):
            snapshot = self.feature_engine.update_closed_bar(bar)
            candidate = self.composer.on_bar(bar, snapshot)
            if candidate is None:
                continue
            event = self.signal_service.create_event(candidate)
            signal_ids.append(self.signal_repository.append_signal(event))
        return BacktestResult(
            bars_seen=len(bars),
            signals_created=len(signal_ids),
            signal_ids=tuple(signal_ids),
        )

    @classmethod
    def create_default(
        cls,
        *,
        feature_engine: RollingFeatureEngine,
        signal_service: SignalService,
        signal_repository: InMemorySignalRepository,
        runtime: StrategyRuntime | None = None,
        composer: StrategyComposer | None = None,
    ) -> "BacktestRunner":
        if runtime is None and composer is None:
            runtime = RuleStrategyRuntime()
        if composer is None:
            assert runtime is not None
            composer = StrategyComposer.single(runtime)
        return cls(
            feature_engine=feature_engine,
            strategy_runtime=composer,
            signal_service=signal_service,
            signal_repository=signal_repository,
        )