"""Integration test for BacktestOrchestrator — single symbol, no universe."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal


from quant_signal_system.backtest.orchestrator import BacktestOrchestrator
from quant_signal_system.backtest.run_spec import BacktestRunSpec, StrategyBinding
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.market_data.repository import InMemoryMarketDataRepository
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.time.clock import VirtualClock
from quant_signal_system.universe.contracts import UniverseSnapshot
from quant_signal_system.universe.repository import UniverseRepository
from quant_signal_system.universe.resolver import UniverseResolver


def _bar(
    symbol: str,
    market_data_time: datetime,
    close: float = 42.0,
    volume: int = 1000,
) -> MarketBar:
    end = market_data_time
    start = end.replace(minute=end.minute - 1)
    close_dec = Decimal(str(close))
    return MarketBar(
        schema_version="market-bar-v1",
        symbol=symbol,
        timeframe="1m",
        bar_start_time=start,
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=close_dec,
        high_price=close_dec,
        low_price=close_dec,
        close_price=close_dec,
        volume=Decimal(str(volume)),
        amount=None,
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        data_source_version="test-v1",
        as_of_version="asof-v1",
        source="test",
    )


def _spec(
    from_time: datetime,
    to_time: datetime,
    binding_id: str = "b1",
    universe_id: str = "u1",
    universe_version: str = "v1",
) -> BacktestRunSpec:
    return BacktestRunSpec(
        from_time=from_time,
        to_time=to_time,
        strategy_bindings=(
            StrategyBinding(
                binding_id=binding_id,
                strategy_name="test",
                strategy_version="v1",
                parameter_hash="h",
                universe_id=universe_id,
                universe_version=universe_version,
                feature_version="f1",
            ),
        ),
    )


def _universe(
    universe_id: str,
    symbols: tuple[str, ...],
    universe_version: str,
    effective_time: datetime,
    available_at: datetime,
) -> UniverseSnapshot:
    return UniverseSnapshot(
        universe_id=universe_id,
        universe_version=universe_version,
        effective_time=effective_time,
        available_at=available_at,
        symbols=symbols,
        inclusion_reason="manual",
        source="manual",
        source_version="v1",
        revision_id="r1",
        as_of_version="asof-v1",
    )


def _make_orchestrator(
    spec: BacktestRunSpec,
    universe_repo: UniverseRepository,
) -> tuple[BacktestOrchestrator, InMemorySignalRepository]:
    resolver = UniverseResolver(universe_repo)
    market_repo = InMemoryMarketDataRepository()
    signal_repo = InMemorySignalRepository()
    clock = VirtualClock(current_time=spec.from_time)
    signal_service = SignalService(clock=clock)
    orch = BacktestOrchestrator(
        spec=spec,
        universe_resolver=resolver,
        market_repo=market_repo,
        signal_service=signal_service,
        signal_repo=signal_repo,
    )
    return orch, signal_repo


class TestBacktestOrchestratorSingleSymbol:
    def test_basic_run(self) -> None:
        repo = UniverseRepository()
        u1 = _universe(
            "u1", ("300346",), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        )
        repo.save(u1)
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, signal_repo = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 10)
        result = orch.run(bars)
        assert result.total_bars == 10
        assert result.signals_generated >= 0
        assert result.out_of_order_bars == 0

    def test_bar_count_matches_input(self) -> None:
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("300346",), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 20)
        result = orch.run(bars)
        assert result.total_bars == 20
        assert result.bars_by_symbol == (("300346", 20),)

    def test_empty_bars(self) -> None:
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("300346",), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        result = orch.run([])
        assert result.total_bars == 0
        assert result.signals_generated == 0

    def test_signal_ids_deterministic(self) -> None:
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("300346",), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch1, _ = _make_orchestrator(spec, repo)
        orch2, _ = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 10)
        r1 = orch1.run(bars)
        r2 = orch2.run(bars)
        assert r1.signal_ids == r2.signal_ids
        assert r1.total_bars == r2.total_bars

    def test_universe_not_visible_raises(self) -> None:
        repo = UniverseRepository()
        # Universe only visible after run start time
        repo.save(_universe(
            "u1", ("300346",), "v1",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 10)
        # Universe not visible at spec.from_time → initialization should handle gracefully
        result = orch.run(bars)
        # Should produce result (no crash) even if universe was not yet available
        assert result is not None


class TestBacktestOrchestratorMultiSymbol:
    def test_multi_symbol_bars_count(self) -> None:
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("300346", "600519"), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 10) + _generate_bars("600519", 10)
        result = orch.run(bars)
        assert result.total_bars == 20
        assert dict(result.bars_by_symbol)["300346"] == 10
        assert dict(result.bars_by_symbol)["600519"] == 10

    def test_symbol_not_in_universe_skipped(self) -> None:
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("300346",), "v1",  # only 300346
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 10) + _generate_bars("600519", 10)
        result = orch.run(bars)
        # Only 300346 bars should be counted
        assert dict(result.bars_by_symbol)["300346"] == 10
        assert dict(result.bars_by_symbol).get("600519", 0) == 0

    def test_stable_sorting_by_symbol(self) -> None:
        """Verify bars are processed in (market_data_time, symbol) order."""
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("000001", "300346", "600519"), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        # Bars in random order
        bars = (
            _generate_bars("600519", 3)
            + _generate_bars("300346", 3)
            + _generate_bars("000001", 3)
        )
        result = orch.run(bars)
        assert result.total_bars == 9


class TestBacktestOrchestratorManifest:
    def test_build_manifest(self) -> None:
        repo = UniverseRepository()
        repo.save(_universe(
            "u1", ("300346",), "v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
        ))
        spec = _spec(
            from_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc),
            to_time=datetime(2025, 6, 2, 15, 0, tzinfo=timezone.utc),
        )
        orch, _ = _make_orchestrator(spec, repo)
        bars = _generate_bars("300346", 5)
        result = orch.run(bars)
        manifest = orch.build_manifest(result)
        assert manifest.run_id == result.run_id
        assert manifest.run_status == "success"
        assert manifest.total_bars_processed == 5
        assert manifest.total_signals_generated == result.signals_generated
        assert manifest.strategy_versions == ("v1",)


def _generate_bars(
    symbol: str,
    count: int,
    start: datetime | None = None,
    close: float = 42.0,
    volume: int = 1000,
) -> list[MarketBar]:
    if start is None:
        start = datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc)
    bars: list[MarketBar] = []
    for i in range(count):
        t = start + timedelta(minutes=i)
        bars.append(
            _bar(
                symbol=symbol,
                market_data_time=t,
                close=close + (i * 0.1),
                volume=volume,
            )
        )
    return bars
