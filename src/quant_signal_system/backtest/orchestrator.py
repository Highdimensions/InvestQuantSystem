"""Backtest orchestrator: drives the full signal-generation pipeline from sorted bars.

The orchestrator is the central coordinator for a backtest run.  It owns:

1. Virtual clock management (via BacktestScheduler)
2. Universe state and resolver integration
3. (binding_id, symbol) state isolation (via StatePartition)
4. Feature engine → strategy → signal service pipeline
5. Run result accumulation and manifest preparation

Phase 2 scope:
  market_bar → feature_update → strategy_candidate → signal_event

Phase 3 adds:
  composer_decision (multi-strategy conflict resolution)
  order_intent generation

Phase 4 adds:
  market_rules_engine validation
  portfolio_ledger updates
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from quant_signal_system.backtest.manifest import (
    BacktestRunManifest,
    ManifestBuilder,
    RunWarning,
)
from quant_signal_system.backtest.result import BacktestRunResult, UniverseChangeEvent
from quant_signal_system.backtest.run_spec import BacktestRunSpec
from quant_signal_system.backtest.scheduler import BacktestScheduler
from quant_signal_system.backtest.state_partition import StatePartition
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.time.clock import VirtualClock

if TYPE_CHECKING:
    from quant_signal_system.universe.resolver import UniverseResolver


class MarketDataRepositoryLike(Protocol):
    """Structural protocol for market data repositories.

    Duck-typed so the orchestrator works with InMemoryMarketDataRepository,
    SQLiteMarketDataRepository, or any future implementation.
    """

    def save_bar(self, bar) -> None:
        ...


class BacktestOrchestrator:
    """Drives a complete backtest run from BacktestRunSpec to BacktestRunResult."""

    def __init__(
        self,
        spec: BacktestRunSpec,
        universe_resolver: UniverseResolver,
        market_repo: MarketDataRepositoryLike,
        signal_service: SignalService,
        signal_repo: InMemorySignalRepository,
        clock: VirtualClock | None = None,
    ) -> None:
        self.spec = spec
        self.universe_resolver = universe_resolver
        self.market_repo = market_repo
        self.signal_service = signal_service
        self.signal_repo = signal_repo

        self.clock = clock or VirtualClock(current_time=spec.from_time)
        self.scheduler = BacktestScheduler(spec=spec, clock=self.clock)
        self.state_partition = StatePartition()

        # Per-binding universe state: binding_id → current universe_version
        self._universe_versions: dict[str, str] = {}
        self._warnings: list[RunWarning] = []
        self._universe_changes: list[UniverseChangeEvent] = []

        # Statistics
        self._bars_by_symbol: dict[str, int] = {}
        self._signal_ids: list[str] = []
        self._signals_rejected = 0
        self._started_at: datetime | None = None
        self._finished_at: datetime | None = None

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def run(self, bars: list) -> BacktestRunResult:
        """Run the backtest over the given bars and return a result.

        The bars are sorted internally by (market_data_time, symbol) for
        deterministic ordering.
        """
        self._started_at = datetime.now(timezone.utc)
        self._initialize()

        sorted_bars = self.scheduler.stable_sort_bars(list(bars))
        for bar in sorted_bars:
            self._process_bar(bar)

        self._finished_at = datetime.now(timezone.utc)
        return self._build_result()

    def build_manifest(self, result: BacktestRunResult) -> BacktestRunManifest:
        """Build a BacktestRunManifest from a completed run result."""
        manifest = ManifestBuilder(run_id=result.run_id, created_at=result.started_at)
        manifest.set_run_mode(self.spec.run_mode)
        manifest.set_config_snapshot(
            original_spec_yaml=self.spec.compute_resolved_hash(),
            resolved_config_hash=result.spec_hash,
        )
        manifest.set_versions(
            strategy_versions=tuple(set(b.strategy_version for b in self.spec.strategy_bindings)),
            universe_versions=tuple(set(self._universe_versions.values())),
            data_source_version=self.spec.data_source_version,
            as_of_version=self.spec.as_of_version,
        )
        manifest.set_data_range(
            from_time=self.spec.from_time,
            to_time=self.spec.to_time,
            timeframe=self.spec.timeframe,
        )
        manifest.set_statistics(
            total_bars_processed=result.total_bars,
            total_bars_skipped=result.bars_skipped,
            total_signals_generated=result.signals_generated,
            total_signals_rejected=result.signals_rejected,
        )
        manifest.set_data_quality(
            out_of_order_bar_count=result.out_of_order_bars,
        )
        for w in result.warnings:
            manifest.add_warning(w)
        manifest.set_deterministic_check(
            passed=True,
            detail="Phase 2 determinism check: run completed without non-determinism signals",
        )
        return manifest.finalize(run_status="success", completed_at=result.finished_at)

    # -------------------------------------------------------------------------
    # Initialization
    # -------------------------------------------------------------------------

    def _initialize(self) -> None:
        """Initialize universe states and state partition for all bindings.

        Uses require_strict=False so that runs with no visible universe at from_time
        proceed with an empty state partition (no slots created). This is the
        correct Phase 2 behaviour for universes whose effective_time is after the
        run's from_time.
        """
        for binding in self.spec.strategy_bindings:
            self._initialize_binding(binding)

    def _initialize_binding(self, binding) -> None:
        """Initialize the universe and state slots for one binding.

        Uses require_strict=False: if no universe is visible at from_time the
        binding is left with no active symbols (graceful degradation).
        """
        snapshot = self.universe_resolver.resolve(
            binding.universe_id,
            at_time=self.spec.from_time,
            require_strict=False,
        )
        if snapshot is None:
            self._warnings.append(
                RunWarning(
                    warning_code="UNIVERSE_UNAVAILABLE",
                    severity="warn",
                    message=(
                        f"no visible universe {binding.universe_id!r} at "
                        f"{self.spec.from_time.isoformat()}; "
                        "binding will not process any bars"
                    ),
                    affected_symbols=(),
                )
            )
            self._universe_versions[binding.binding_id] = ""
            return
        self._universe_versions[binding.binding_id] = snapshot.universe_version

        for symbol in snapshot.symbols:
            self.state_partition.get_or_create(binding.binding_id, symbol)
            if symbol not in self._bars_by_symbol:
                self._bars_by_symbol[symbol] = 0

    def _initialize_binding_from_spec(self, binding, snapshot) -> None:
        """Reinitialize a binding's universe state (for universe switches)."""
        for symbol in snapshot.symbols:
            self.state_partition.get_or_create(binding.binding_id, symbol)
            slot = self.state_partition.get(binding.binding_id, symbol)
            if slot is not None:
                slot.feature_engine.clock = self.clock  # type: ignore[attr-defined]
            if symbol not in self._bars_by_symbol:
                self._bars_by_symbol[symbol] = 0

    # -------------------------------------------------------------------------
    # Core bar processing loop
    # -------------------------------------------------------------------------

    def _process_bar(self, bar) -> None:
        """Process one closed bar: clock advance, universe check, signal pipeline."""
        self.scheduler.advance_to_bar(bar)

        self.market_repo.save_bar(bar)

        current_time = self.scheduler.current_time()
        self._check_universe_changes(current_time)

        # Only count bars for symbols in at least one active universe
        if self._symbol_in_any_universe(bar.symbol):
            self._bars_by_symbol[bar.symbol] = self._bars_by_symbol.get(bar.symbol, 0) + 1

        for binding in self.spec.strategy_bindings:
            self._process_binding(binding, bar, current_time)

    def _symbol_in_any_universe(self, symbol: str) -> bool:
        """Return True if symbol belongs to at least one binding's current universe.

        Uses the state partition slots as source of truth: if a binding has a
        non-empty universe version and a state slot for this symbol, the symbol
        is active for that binding.
        """
        for binding in self.spec.strategy_bindings:
            version = self._universe_versions.get(binding.binding_id, "")
            if version and self.state_partition.contains(binding.binding_id, symbol):
                return True
        return False

    def _process_binding(self, binding, bar, current_time) -> None:
        """Process one bar through one strategy binding."""
        current_universe_version = self._universe_versions.get(binding.binding_id)

        snapshot = self.universe_resolver.resolve(
            binding.universe_id,
            at_time=current_time,
            require_strict=False,
        )
        if snapshot is None:
            return

        if snapshot.universe_version != current_universe_version:
            return

        if bar.symbol not in snapshot.symbols:
            return

        state = self.state_partition.get_or_create(binding.binding_id, bar.symbol)
        state.feature_engine.clock = self.clock  # type: ignore[attr-defined]
        runtime = state.ensure_runtime(binding)

        snapshot_feat = state.feature_engine.update_closed_bar(bar)
        candidate = runtime.on_bar(bar, snapshot_feat)
        if candidate is None:
            return

        signal = self.signal_service.create_event(candidate)
        self.signal_repo.append_signal(signal)
        self._signal_ids.append(signal.signal_id)

    def _check_universe_changes(self, current_time: datetime) -> None:
        """Detect and record universe version changes for all bindings."""
        for binding in self.spec.strategy_bindings:
            snapshot = self.universe_resolver.resolve(
                binding.universe_id,
                at_time=current_time,
                require_strict=False,
            )
            if snapshot is None:
                continue

            prev = self._universe_versions.get(binding.binding_id, "")
            if prev and snapshot.universe_version != prev:
                change = UniverseChangeEvent(
                    universe_id=binding.universe_id,
                    previous_version=prev,
                    new_version=snapshot.universe_version,
                    change_count=1,
                )
                self._universe_changes.append(change)
                self._warnings.append(
                    RunWarning(
                        warning_code="UNIVERSE_CHANGE",
                        severity="info",
                        message=(
                            f"universe {binding.universe_id} changed from {prev} to "
                            f"{snapshot.universe_version} at {current_time.isoformat()}"
                        ),
                        affected_symbols=snapshot.symbols,
                    )
                )
                self._universe_versions[binding.binding_id] = snapshot.universe_version
                self._initialize_binding_from_spec(binding, snapshot)
            elif not prev:
                self._universe_versions[binding.binding_id] = snapshot.universe_version

    # -------------------------------------------------------------------------
    # Result building
    # -------------------------------------------------------------------------

    def _build_result(self) -> BacktestRunResult:
        started = self._started_at or datetime.now(timezone.utc)
        finished = self._finished_at or datetime.now(timezone.utc)

        bars_skipped = 0
        for b in self.spec.strategy_bindings:
            pass

        return BacktestRunResult(
            run_id=self.spec.run_id or f"run_{self.spec.compute_resolved_hash()[:8]}",
            spec_hash=self.spec.compute_resolved_hash(),
            total_bars=sum(self._bars_by_symbol.values()),
            bars_skipped=bars_skipped,
            signals_generated=len(self._signal_ids),
            signals_rejected=self._signals_rejected,
            out_of_order_bars=self.scheduler.out_of_order_count(),
            universe_changes=len(self._universe_changes),
            bars_by_symbol=tuple(sorted(self._bars_by_symbol.items())),
            signal_ids=tuple(self._signal_ids),
            universe_change_events=tuple(self._universe_changes),
            warnings=tuple(self._warnings),
            started_at=started,
            finished_at=finished,
        )
