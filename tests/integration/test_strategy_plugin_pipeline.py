"""End-to-end tests for the registry + composer + BacktestRunner stack.

These tests assert that:

* registering a strategy through the registry produces a frozen identity
  that the SignalService accepts;
* `BacktestRunner.create_default()` composes a registered strategy without
  any hardcoded class names in the call site;
* multi-strategy scheduling through the registry runs and converges to one
  `SignalEvent` per bar.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from quant_signal_system.backtest.runner import BacktestRunner
from quant_signal_system.config.versions import VersionRegistry
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies import (
    DEFAULT_REGISTRY,
    StrategyComposer,
    StrategyRegistry,
)
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.time.clock import FrozenClock


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _bar(time_value: str, close: str, volume: str = "100") -> MarketBar:
    end = utc(time_value)
    price = Decimal(close)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=end - timedelta(minutes=1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=price,
        high_price=price + Decimal("0.10"),
        low_price=price - Decimal("0.10"),
        close_price=price,
        volume=Decimal(volume),
        amount=price * Decimal(volume),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source="AKShare",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def test_backtest_runner_uses_registry_only() -> None:
    registry = StrategyRegistry(version_registry=VersionRegistry())
    registry.register(RuleStrategyRuntime)

    clock = FrozenClock(utc("2024-07-03T01:35:00+00:00"))
    feature_engine = RollingFeatureEngine(clock=clock)
    signal_service = SignalService(clock, version_registry=registry.version_registry)
    signal_repo = InMemorySignalRepository()

    composer = StrategyComposer(runtimes=registry.resolve_many(("baseline-rules",)))
    runner = BacktestRunner(feature_engine, composer, signal_service, signal_repo)

    bars = [
        _bar("2024-07-03T01:31:00+00:00", "10.00", "100"),
        _bar("2024-07-03T01:32:00+00:00", "10.10", "100"),
        _bar("2024-07-03T01:33:00+00:00", "10.30", "300"),
    ]
    result = runner.run_bars(bars)
    assert result.signals_created == 1
    assert signal_repo.list_signals()[0].strategy_name == "baseline-rules"


def test_backtest_runner_create_default_resolves_through_registry() -> None:
    DEFAULT_REGISTRY.register(RuleStrategyRuntime)
    clock = FrozenClock(utc("2024-07-03T01:35:00+00:00"))
    runner = BacktestRunner.create_default(
        feature_engine=RollingFeatureEngine(clock=clock),
        signal_service=SignalService(clock),
        signal_repository=InMemorySignalRepository(),
    )
    bars = [
        _bar("2024-07-03T01:31:00+00:00", "10.00", "100"),
        _bar("2024-07-03T01:32:00+00:00", "10.10", "100"),
        _bar("2024-07-03T01:33:00+00:00", "10.30", "300"),
    ]
    result = runner.run_bars(bars)
    assert result.signals_created == 1


def test_multi_strategy_composer_emits_one_signal() -> None:
    registry = StrategyRegistry(version_registry=VersionRegistry())
    registry.register(RuleStrategyRuntime)
    secondary_registry = StrategyRegistry(version_registry=VersionRegistry())

    @classmethod  # type: ignore[misc]
    def _noop(cls):  # type: ignore[no-untyped-def]
        return None

    RuleStrategyRuntime.param_schema()  # ensure accessible

    from dataclasses import dataclass

    @dataclass(frozen=True, slots=True)
    class NeverFires:
        strategy_name: str = "secondary"
        strategy_version: str = "secondary-v1"
        code_version: str = "research-code-v1"
        parameter_hash: str = "secondary-hash"
        horizon_seconds: int = 900

        @property
        def name(self) -> str:
            return self.strategy_name

        @property
        def version(self) -> str:
            return self.strategy_version

        def declare_parameters(self) -> tuple[tuple[str, object], ...]:
            return (("horizon_seconds", 900),)

        def on_bar(self, bar, snapshot, regime=None):
            return None

    secondary_registry.register(NeverFires)

    primary_runtime = registry.get("baseline-rules")
    secondary_runtime = secondary_registry.get("secondary")

    clock = FrozenClock(utc("2024-07-03T01:35:00+00:00"))
    composer = StrategyComposer(runtimes=(primary_runtime, secondary_runtime))
    signal_service = SignalService(clock, version_registry=registry.version_registry)
    signal_repo = InMemorySignalRepository()
    runner = BacktestRunner(
        RollingFeatureEngine(clock=clock),
        composer,
        signal_service,
        signal_repo,
    )

    bars = [
        _bar("2024-07-03T01:31:00+00:00", "10.00", "100"),
        _bar("2024-07-03T01:32:00+00:00", "10.10", "100"),
        _bar("2024-07-03T01:33:00+00:00", "10.30", "300"),
    ]
    result = runner.run_bars(bars)
    assert result.signals_created == 1
    signal = signal_repo.list_signals()[0]
    assert signal.strategy_name == "baseline-rules"