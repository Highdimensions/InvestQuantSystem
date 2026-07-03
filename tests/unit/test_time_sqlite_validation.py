from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.market_data.akshare_validation import AKShareValidator
from quant_signal_system.market_data.sqlite_repository import SQLiteMarketDataRepository
from quant_signal_system.time.clock import FrozenClock
from quant_signal_system.time.trading_calendar import SimpleAshareTradingCalendar


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def bar(time_value: str, *, version: str = "akshare-exploration-v1") -> MarketBar:
    end = utc(time_value)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=end - timedelta(minutes=1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=Decimal("10.00"),
        high_price=Decimal("10.20"),
        low_price=Decimal("9.90"),
        close_price=Decimal("10.10"),
        volume=Decimal("10000"),
        amount=Decimal("101000"),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source="AKShare",
        data_source_version=version,
        as_of_version="asof-research-v1",
    )


def test_frozen_clock_and_simple_ashare_calendar_are_deterministic() -> None:
    clock = FrozenClock(utc("2024-07-03T01:31:00+00:00"))
    calendar = SimpleAshareTradingCalendar(holidays=frozenset({date(2024, 7, 4)}))

    assert calendar.is_session_time(clock.now())
    clock.advance(timedelta(minutes=1))
    assert clock.now() == utc("2024-07-03T01:32:00+00:00")
    assert calendar.next_evaluation_time(clock.now(), 60) == utc("2024-07-03T01:33:00+00:00")


def test_sqlite_market_data_repository_persists_versioned_bars(tmp_path) -> None:
    repo = SQLiteMarketDataRepository(tmp_path / "market.db")
    first = bar("2024-07-03T01:31:00+00:00")

    assert repo.save_bar(first) == "inserted"
    assert repo.save_bar(first) == "duplicate"
    rows = repo.read_bars(
        symbol="000001",
        from_time=utc("2024-07-03T01:30:00+00:00"),
        to_time=utc("2024-07-03T01:32:00+00:00"),
        timeframe="1m",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )

    assert rows == [first]


def test_akshare_validator_is_single_source_only() -> None:
    class Source:
        profile = type(
            "Profile",
            (),
            {"data_source_version": "akshare-exploration-v1", "as_of_version": "asof-research-v1"},
        )()

        def _akshare_symbol(self, symbol):
            return symbol

        def read_with_quarantine(self, *, symbols, from_time, to_time):
            return [bar("2024-07-03T01:31:00+00:00")]

    result = AKShareValidator(Source()).validate_window(
        symbols=["000001"],
        from_time=utc("2024-07-03T01:30:00+00:00"),
        to_time=utc("2024-07-03T01:32:00+00:00"),
    )

    assert result.passed
    assert result.bars_count == 1

