"""Backtest runner, run specification, manifest, and orchestrator."""

from quant_signal_system.backtest.manifest import (
    ArtifactRef,
    AssertionResult,
    BacktestRunManifest,
    ManifestBuilder,
    RunWarning,
)
from quant_signal_system.backtest.orchestrator import BacktestOrchestrator
from quant_signal_system.backtest.result import BacktestRunResult, UniverseChangeEvent
from quant_signal_system.backtest.runner import BacktestResult, BacktestRunner
from quant_signal_system.backtest.run_spec import (
    BacktestRunSpec,
    BacktestRunSpecLoader,
    BacktestRunSpecValidationError,
    StrategyBinding,
)
from quant_signal_system.backtest.scheduler import BacktestScheduler
from quant_signal_system.backtest.state_partition import StatePartition, StrategyBindingState

__all__ = [
    # runner (Phase 0)
    "BacktestResult",
    "BacktestRunner",
    # run_spec (Phase 1)
    "BacktestRunSpec",
    "BacktestRunSpecLoader",
    "BacktestRunSpecValidationError",
    "StrategyBinding",
    # manifest (Phase 1)
    "BacktestRunManifest",
    "ManifestBuilder",
    "RunWarning",
    "ArtifactRef",
    "AssertionResult",
    # orchestrator (Phase 2)
    "BacktestOrchestrator",
    # scheduler (Phase 2)
    "BacktestScheduler",
    # state partition (Phase 2)
    "StatePartition",
    "StrategyBindingState",
    # result (Phase 2)
    "BacktestRunResult",
    "UniverseChangeEvent",
]

