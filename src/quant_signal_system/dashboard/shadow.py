"""Local shadow-run control for the research dashboard.

The shadow runner no longer hardcodes any strategy class or version string.
Strategies are resolved through the supplied `StrategyRegistry` (defaulting
to the global `DEFAULT_REGISTRY`) by name. One or more strategy names can
be requested; a `StrategyComposer` aggregates them with the default
priority/confidence policy.

The run state captures each strategy's identity as a composite key
``name@version@parameter_hash@code_version`` so the dashboard can audit
which strategies were scheduled at the time the run started.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from quant_signal_system.config.data_source import akshare_exploration_profile
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.market_data.akshare_source import AKShareMarketDataSource
from quant_signal_system.market_data.sqlite_repository import SQLiteMarketDataRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.signals.sqlite_repository import SQLiteSignalRepository
from quant_signal_system.strategies.composer import ConflictPolicy, StrategyComposer
from quant_signal_system.strategies.registry import StrategyRegistry, DEFAULT_REGISTRY
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.strategies._examples.momentum_v1 import MomentumV1Strategy
from quant_signal_system.time.clock import SystemClock

DEFAULT_STRATEGY_NAMES: tuple[str, ...] = ("baseline-rules",)

_STRATEGIES_BOOTSTRAPPED = False


def _ensure_default_strategies_registered() -> None:
    """Register built-in strategies into DEFAULT_REGISTRY once per process."""
    global _STRATEGIES_BOOTSTRAPPED  # noqa: PLW0603
    if _STRATEGIES_BOOTSTRAPPED:
        return
    _STRATEGIES_BOOTSTRAPPED = True
    import pathlib
    import quant_signal_system

    pkg_root = pathlib.Path(quant_signal_system.__file__).parent

    yaml_path = pkg_root / "strategies" / "baseline_rules.yaml"
    DEFAULT_REGISTRY.register(
        RuleStrategyRuntime,
        yaml_path=yaml_path,
        strategy_version="baseline-rules-v1",
        code_version="research-code-v1",
    )

    DEFAULT_REGISTRY.register(
        MomentumV1Strategy,
        params={"return_threshold": 0.005, "horizon_seconds": 900},
        strategy_version="momentum-v1",
        code_version="research-code-v1",
    )


def _freeze_key(name: str, version: str, parameter_hash: str, code_version: str) -> str:
    return f"{name}@{version}@{parameter_hash}@{code_version}"


@dataclass(slots=True)
class ShadowRunState:
    run_id: str
    symbol: str
    timeframe: str
    strategy_versions: tuple[str, ...]
    data_source_version: str
    as_of_version: str
    from_time: str
    to_time: str
    status: str
    started_at: str
    stopped_at: str | None = None
    bars_seen: int = 0
    signals_created: int = 0
    last_error: str | None = None
    _stop_requested: bool = field(default=False, repr=False)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("_stop_requested", None)
        return payload


class ShadowRunManager:
    def __init__(
        self,
        *,
        market_repository: SQLiteMarketDataRepository,
        signal_repository: SQLiteSignalRepository,
        registry: StrategyRegistry | None = None,
        default_strategy_names: tuple[str, ...] = DEFAULT_STRATEGY_NAMES,
    ) -> None:
        self._market_repository = market_repository
        self._signal_repository = signal_repository
        self._registry = registry or DEFAULT_REGISTRY
        self._default_strategy_names = default_strategy_names
        self._runs: dict[str, ShadowRunState] = {}
        self._lock = threading.Lock()

    def list_runs(self) -> list[dict[str, object]]:
        with self._lock:
            return [state.to_dict() for state in sorted(self._runs.values(), key=lambda item: item.started_at)]

    def start_run(
        self,
        *,
        symbol: str,
        timeframe: str,
        from_time: datetime,
        to_time: datetime,
        data_source_version: str = "akshare-exploration-v1",
        as_of_version: str = "asof-research-v1",
        strategy_names: tuple[str, ...] | None = None,
        conflict_policy: ConflictPolicy = ConflictPolicy.PRIORITY_MAX_CONFIDENCE,
    ) -> ShadowRunState:
        run_id = uuid.uuid4().hex[:16]
        names = strategy_names or self._default_strategy_names
        if not names:
            raise ValueError("at least one strategy name must be supplied")

        composer = self._registry.resolve_many(names)
        if len(composer) != len(names):
            missing = set(names) - {runtime.name for runtime in composer}
            raise KeyError(f"unregistered strategies: {sorted(missing)}")

        wrapped = StrategyComposer(runtimes=tuple(composer), policy=conflict_policy)
        freeze_keys = tuple(
            _freeze_key(
                runtime.name,
                runtime.version,
                runtime.parameter_hash,
                runtime.code_version,
            )
            for runtime in wrapped.runtimes
        )
        state = ShadowRunState(
            run_id=run_id,
            symbol=symbol,
            timeframe=timeframe,
            strategy_versions=freeze_keys,
            data_source_version=data_source_version,
            as_of_version=as_of_version,
            from_time=from_time.isoformat(),
            to_time=to_time.isoformat(),
            status="STARTING",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._runs[run_id] = state
        thread = threading.Thread(
            target=self._run_shadow,
            args=(state, from_time, to_time, wrapped),
            name=f"shadow-run-{run_id}",
            daemon=True,
        )
        thread.start()
        return state

    def stop_run(self, run_id: str) -> ShadowRunState:
        with self._lock:
            state = self._runs[run_id]
            state._stop_requested = True
            if state.status in {"STARTING", "RUNNING"}:
                state.status = "STOPPING"
            return state

    def _run_shadow(
        self,
        state: ShadowRunState,
        from_time: datetime,
        to_time: datetime,
        composer: StrategyComposer,
    ) -> None:
        try:
            self._set_status(state.run_id, "RUNNING")
            bars = list(
                AKShareMarketDataSource(
                    profile=akshare_exploration_profile(
                        frequency=state.timeframe,
                        data_source_version=state.data_source_version,
                        as_of_version=state.as_of_version,
                    )
                ).read(
                    symbols=[state.symbol],
                    from_time=from_time,
                    to_time=to_time,
                )
            )
            self._process_bars(state, bars, composer)
            with self._lock:
                if state._stop_requested:
                    state.status = "STOPPED"
                elif state.status not in {"FAILED", "STOPPED"}:
                    state.status = "COMPLETED"
                state.stopped_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            with self._lock:
                state.status = "FAILED"
                state.last_error = str(exc)
                state.stopped_at = datetime.now(timezone.utc).isoformat()

    def _process_bars(
        self,
        state: ShadowRunState,
        bars: list[MarketBar],
        composer: StrategyComposer,
    ) -> None:
        clock = SystemClock()
        feature_engine = RollingFeatureEngine(clock=clock)
        signal_service = SignalService(clock)
        for bar in sorted(bars, key=lambda item: item.market_data_time):
            with self._lock:
                if state._stop_requested:
                    state.status = "STOPPED"
                    return
            self._market_repository.save_bar(bar)
            snapshot = feature_engine.update_closed_bar(bar)
            candidate = composer.on_bar(bar, snapshot)
            with self._lock:
                state.bars_seen += 1
            if candidate is None:
                continue
            event = signal_service.create_event(candidate)
            self._signal_repository.append_signal(event)
            with self._lock:
                state.signals_created += 1

    def _set_status(self, run_id: str, status: str) -> None:
        with self._lock:
            self._runs[run_id].status = status