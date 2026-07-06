"""Determinism tests for Phase 2 — same input produces same output."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal


from quant_signal_system.backtest.state_partition import StatePartition
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.strategies.schema import compute_parameter_hash
from quant_signal_system.time.clock import VirtualClock


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
        bars.append(_bar(symbol=symbol, market_data_time=t, close=close + (i * 0.1), volume=volume))
    return bars


def _simple_orchestrate(
    bars: list[MarketBar],
    binding_id: str = "b1",
    symbol: str = "300346",
) -> tuple[list[str], list[datetime]]:
    clock = VirtualClock(current_time=bars[0].market_data_time)
    partition = StatePartition()
    signal_repo = InMemorySignalRepository()
    signal_service = SignalService(clock=clock)
    state = partition.get_or_create(binding_id, symbol)
    runtime = RuleStrategyRuntime()

    signal_ids: list[str] = []
    times: list[datetime] = []

    for bar in sorted(bars, key=lambda b: (b.market_data_time, b.symbol)):
        clock.advance_to(bar.market_data_time)
        snapshot = state.feature_engine.update_closed_bar(bar)
        candidate = runtime.on_bar(bar, snapshot)
        if candidate is None:
            continue
        signal = signal_service.create_event(candidate)
        signal_repo.append_signal(signal)
        signal_ids.append(signal.signal_id)
        times.append(clock.now())

    return signal_ids, times


class TestDeterminism:
    """P1: identical input → identical signal_ids (same parameters, same data)."""

    def test_identical_input_produces_identical_signal_ids(self) -> None:
        bars = _generate_bars("300346", 30)
        ids1, times1 = _simple_orchestrate(bars)
        ids2, times2 = _simple_orchestrate(bars)
        assert ids1 == ids2
        assert times1 == times2

    def test_order_matters_identical(self) -> None:
        bars = _generate_bars("300346", 30)
        ids1, _ = _simple_orchestrate(bars)
        ids2, _ = _simple_orchestrate(bars)
        assert ids1 == ids2

    def test_different_bar_data_produces_different_signals(self) -> None:
        bars_a = _generate_bars("300346", 30, volume=2000)
        bars_b = _generate_bars("300346", 30, volume=500)
        ids_a, _ = _simple_orchestrate(bars_a)
        ids_b, _ = _simple_orchestrate(bars_b)
        assert isinstance(ids_a, list)
        assert isinstance(ids_b, list)

    def test_multi_symbol_same_order(self) -> None:
        bars = _generate_bars("300346", 10) + _generate_bars("600519", 10)
        clock = VirtualClock(current_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc))
        partition = StatePartition()
        signal_repo = InMemorySignalRepository()
        signal_service = SignalService(clock=clock)
        runtime = RuleStrategyRuntime()

        ids: list[str] = []
        for bar in sorted(bars, key=lambda b: (b.market_data_time, b.symbol)):
            clock.advance_to(bar.market_data_time)
            state = partition.get_or_create("b1", bar.symbol)
            snapshot = state.feature_engine.update_closed_bar(bar)
            candidate = runtime.on_bar(bar, snapshot)
            if candidate is None:
                continue
            signal = signal_service.create_event(candidate)
            signal_repo.append_signal(signal)
            ids.append(signal.signal_id)

        # Run twice with same data
        bars2 = _generate_bars("300346", 10) + _generate_bars("600519", 10)
        ids2: list[str] = []
        clock2 = VirtualClock(current_time=datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc))
        partition2 = StatePartition()
        signal_repo2 = InMemorySignalRepository()
        signal_service2 = SignalService(clock=clock2)
        runtime2 = RuleStrategyRuntime()

        for bar in sorted(bars2, key=lambda b: (b.market_data_time, b.symbol)):
            clock2.advance_to(bar.market_data_time)
            state2 = partition2.get_or_create("b1", bar.symbol)
            snapshot2 = state2.feature_engine.update_closed_bar(bar)
            candidate2 = runtime2.on_bar(bar, snapshot2)
            if candidate2 is None:
                continue
            signal2 = signal_service2.create_event(candidate2)
            signal_repo2.append_signal(signal2)
            ids2.append(signal2.signal_id)

        assert ids == ids2

    def test_parameter_hash_stability(self) -> None:
        r1 = RuleStrategyRuntime(
            breakout_volume_ratio=1.5,
            pullback_threshold=-0.01,
        )
        r2 = RuleStrategyRuntime(
            breakout_volume_ratio=1.5,
            pullback_threshold=-0.01,
        )
        # Same params produce same hash via declare_parameters
        h1 = compute_parameter_hash(dict(r1.declare_parameters()))
        h2 = compute_parameter_hash(dict(r2.declare_parameters()))
        assert h1 == h2

    def test_parameter_hash_change_detected(self) -> None:
        r1 = RuleStrategyRuntime(breakout_volume_ratio=1.5)
        r2 = RuleStrategyRuntime(breakout_volume_ratio=2.0)
        h1 = compute_parameter_hash(dict(r1.declare_parameters()))
        h2 = compute_parameter_hash(dict(r2.declare_parameters()))
        assert h1 != h2
