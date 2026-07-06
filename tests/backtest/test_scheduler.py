"""Tests for backtest/scheduler.py."""

from __future__ import annotations

from datetime import datetime, timezone


from quant_signal_system.backtest.run_spec import BacktestRunSpec, StrategyBinding
from quant_signal_system.backtest.scheduler import BacktestScheduler
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.time.clock import VirtualClock


def _bar(
    symbol: str,
    market_data_time: datetime,
    close: float = 42.0,
) -> MarketBar:
    end = market_data_time
    start = end.replace(minute=end.minute - 1)
    price = close  # float ok; MarketBar fields typed as float in dataclass
    return MarketBar(
        schema_version="market-bar-v1",
        symbol=symbol,
        timeframe="1m",
        bar_start_time=start,
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=price,
        high_price=price,
        low_price=price,
        close_price=price,
        volume=1000,
        amount=None,
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        data_source_version="test-v1",
        as_of_version="asof-v1",
        source="test",
    )


class TestBacktestSchedulerStableSort:
    def test_single_bar(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        bars = [_bar("300346", datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc))]
        sorted_bars = sched.stable_sort_bars(bars)
        assert len(sorted_bars) == 1
        assert sorted_bars[0].symbol == "300346"

    def test_multiple_bars_sorted_by_time(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        bars = [
            _bar("300346", datetime(2025, 6, 2, 9, 32, tzinfo=timezone.utc)),
            _bar("300346", datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc)),
            _bar("300346", datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc)),
        ]
        sorted_bars = sched.stable_sort_bars(bars)
        assert [b.market_data_time for b in sorted_bars] == sorted(
            [b.market_data_time for b in bars]
        )

    def test_same_time_different_symbol_sorted_alpha(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        t = datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc)
        bars = [
            _bar("600519", t),
            _bar("300346", t),
            _bar("000001", t),
        ]
        sorted_bars = sched.stable_sort_bars(bars)
        assert [b.symbol for b in sorted_bars] == ["000001", "300346", "600519"]

    def test_mixed_time_and_symbol(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        bars = [
            _bar("600519", datetime(2025, 6, 2, 9, 32, tzinfo=timezone.utc)),
            _bar("300346", datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc)),
            _bar("000001", datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc)),
            _bar("300346", datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc)),
        ]
        sorted_bars = sched.stable_sort_bars(bars)
        assert [b.symbol for b in sorted_bars] == [
            "300346",  # 9:30
            "000001",  # 9:31
            "300346",  # 9:31
            "600519",  # 9:32
        ]

    def test_empty_list(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        sorted_bars = sched.stable_sort_bars([])
        assert sorted_bars == []


class TestBacktestSchedulerAdvance:
    def test_advance_to_bar(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        bar = _bar("300346", datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc))
        t = sched.advance_to_bar(bar)
        assert t == datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc)
        assert sched.current_time() == datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc)

    def test_out_of_order_bar_detected(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        bar1 = _bar("300346", datetime(2025, 6, 2, 9, 31, tzinfo=timezone.utc))
        bar2 = _bar("300346", datetime(2025, 6, 2, 9, 30, tzinfo=timezone.utc))  # backward
        sched.advance_to_bar(bar1)
        assert sched.out_of_order_count() == 0
        sched.advance_to_bar(bar2)
        assert sched.out_of_order_count() == 1
        assert sched.last_warning_code() == "OUT_OF_ORDER_BAR"

    def test_forward_bars_no_out_of_order(self) -> None:
        spec = _spec()
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        sched = BacktestScheduler(spec=spec, clock=clock)
        for i in range(10):
            bar = _bar("300346", datetime(2025, 6, 2, 9, 30 + i, tzinfo=timezone.utc))
            sched.advance_to_bar(bar)
        assert sched.out_of_order_count() == 0


def _spec() -> BacktestRunSpec:
    return BacktestRunSpec(
        from_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        to_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
        strategy_bindings=(
            StrategyBinding(
                binding_id="b1",
                strategy_name="test",
                strategy_version="v1",
                parameter_hash="h",
                universe_id="u1",
                universe_version="v1",
                feature_version="f1",
            ),
        ),
    )
