"""Shared orchestration helpers for Phase 7 consistency / fuzz / benchmark tests.

These helpers wrap the real ``BacktestOrchestrator`` and ``RuleStrategyRuntime``
and isolate each test from arbitrary wall-clock and filesystem state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from quant_signal_system.backtest.manifest import (
    ArtifactRef,
    BacktestRunManifest,
    ManifestBuilder,
)
from quant_signal_system.backtest.orchestrator import BacktestOrchestrator
from quant_signal_system.backtest.result import BacktestRunResult
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.time.clock import VirtualClock
from quant_signal_system.universe.contracts import UniverseSnapshot
from quant_signal_system.universe.repository import UniverseRepository
from quant_signal_system.universe.resolver import UniverseResolver


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def make_bar(
    symbol: str,
    market_data_time: datetime,
    *,
    close: float = 42.0,
    volume: int = 1000,
    timeframe: str = "1m",
    is_closed: bool = True,
) -> MarketBar:
    """Build a MarketBar at the given minute boundary (start = end - 1 minute)."""
    if timeframe == "1m":
        start = market_data_time.replace(microsecond=0) - timedelta(minutes=1)
    else:  # default: 1-min
        start = market_data_time - timedelta(minutes=1)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol=symbol,
        timeframe=timeframe,
        bar_start_time=start,
        bar_end_time=market_data_time,
        market_data_time=market_data_time,
        ingest_time=market_data_time,
        open_price=Decimal(str(close)),
        high_price=Decimal(str(close)),
        low_price=Decimal(str(close)),
        close_price=Decimal(str(close)),
        volume=Decimal(str(volume)),
        amount=None,
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=is_closed,
        bar_close_time=market_data_time,
        data_source_version="test-v1",
        as_of_version="asof-v1",
        source="test",
    )


def generate_bars(
    symbol: str,
    count: int,
    *,
    start: datetime | None = None,
    close_delta: float = 0.1,
    base_close: float = 42.0,
    volume: int = 1000,
) -> list[MarketBar]:
    """Generate ``count`` 1-min bars for ``symbol`` with monotonic close drift."""
    if start is None:
        start = utc(2025, 6, 2, 9, 30)
    return [
        make_bar(
            symbol=symbol,
            market_data_time=start + timedelta(minutes=i),
            close=base_close + i * close_delta,
            volume=volume,
        )
        for i in range(count)
    ]


@dataclass(slots=True)
class OrchestrationHarness:
    """Self-contained orchestrator for tests."""

    spec_from: datetime = field(default_factory=lambda: utc(2025, 6, 2, 9, 30))
    spec_to: datetime = field(default_factory=lambda: utc(2025, 6, 2, 10, 30))
    binding_id: str = "b1"
    strategy_name: str = "rule_vol_breakout"
    universe_id: str = "u1"
    universe_version: str = "v1"
    symbols: tuple[str, ...] = ("300346",)

    def build_universe(self) -> UniverseResolver:
        repo = UniverseRepository()
        snap = UniverseSnapshot(
            universe_id=self.universe_id,
            universe_version=self.universe_version,
            effective_time=self.spec_from,
            available_at=self.spec_from,
            symbols=self.symbols,
            inclusion_reason="manual",
            source="manual",
            source_version="test-v1",
            revision_id="test-rev-1",
            as_of_version="asof-v1",
        )
        repo.save(snap)
        return UniverseResolver(repo)

    def build_orchestrator(self) -> BacktestOrchestrator:
        from quant_signal_system.backtest.run_spec import (
            BacktestRunSpec,
            StrategyBinding,
        )

        spec = BacktestRunSpec(
            from_time=self.spec_from,
            to_time=self.spec_to,
            timeframe="1m",
            data_source_version="test-v1",
            as_of_version="asof-v1",
            strategy_bindings=(
                StrategyBinding(
                    binding_id=self.binding_id,
                    strategy_name=self.strategy_name,
                    strategy_version="v1",
                    parameter_hash="ph1",
                    universe_id=self.universe_id,
                    universe_version=self.universe_version,
                    feature_version="f1",
                ),
            ),
        )

        class _Repo:
            def save_bar(self, bar: object) -> None:
                return None

        # Share a single VirtualClock between the orchestrator and the
        # SignalService so that ``signal.event_time`` tracks the bar's
        # ``market_data_time`` (otherwise SignalService sees a frozen clock
        # while the orchestrator advances, causing validation errors).
        clock = VirtualClock(current_time=self.spec_from)
        signal_service = SignalService(clock=clock)
        orchestrator = BacktestOrchestrator(
            spec=spec,
            universe_resolver=self.build_universe(),
            market_repo=_Repo(),  # type: ignore[arg-type]
            signal_service=signal_service,
            signal_repo=InMemorySignalRepository(),
            clock=clock,
        )
        return orchestrator

    def run(self, bars: Iterable[MarketBar]) -> BacktestRunResult:
        orchestrator = self.build_orchestrator()
        return orchestrator.run(list(bars))


def build_manifest(signal_count: int, *, run_id: str = "bench-run") -> BacktestRunManifest:
    """Return a representative manifest used in benchmarks."""
    builder = ManifestBuilder(run_id=run_id, created_at=utc(2025, 6, 2, 9, 30))
    builder.set_data_range(utc(2025, 6, 2, 9, 30), utc(2025, 6, 2, 10, 30), "1m")
    builder.set_statistics(total_bars_processed=signal_count, total_signals_generated=signal_count)
    builder.set_deterministic_check(passed=True, detail="phase-7 benchmark fixture")
    return builder.finalize(run_status="success", completed_at=utc(2025, 6, 2, 10, 30))


def write_manifest(manifest: BacktestRunManifest, path: Path) -> ArtifactRef:
    """Write a manifest to ``path`` and return its ``ArtifactRef``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json(), encoding="utf-8")
    import hashlib

    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    return ArtifactRef(
        artifact_name="manifest",
        artifact_path=path.name,
        artifact_type="json",
        checksum_sha256=checksum,
    )


__all__ = [
    "OrchestrationHarness",
    "build_manifest",
    "generate_bars",
    "make_bar",
    "utc",
    "write_manifest",
]
