from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.market_data.reconciliation import MarketDataReconciler
from quant_signal_system.market_data.repository import (
    DuplicatePolicy,
    InMemoryMarketDataRepository,
    VersionConflictError,
)
from quant_signal_system.market_data.replay import MarketDataReplaySource


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def bar(
    *,
    close: str = "10.10",
    source: str = "AKShare",
    version: str = "akshare-exploration-v1",
    time: str = "2026-07-03T01:31:00+00:00",
) -> MarketBar:
    end = utc(time)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=utc("2026-07-03T01:30:00+00:00"),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=Decimal("10.00"),
        high_price=Decimal("10.20"),
        low_price=Decimal("9.90"),
        close_price=Decimal(close),
        volume=Decimal("10000"),
        amount=Decimal("101000"),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source=source,
        data_source_version=version,
        as_of_version="asof-research-v1",
    )


def test_repository_is_append_only_and_duplicate_is_idempotent() -> None:
    repo = InMemoryMarketDataRepository()
    first = bar()

    assert repo.save_bar(first) == "inserted"
    assert repo.save_bar(first) == "duplicate"

    conflicting = replace(first, close_price=Decimal("10.11"))
    with pytest.raises(VersionConflictError):
        repo.save_bar(conflicting)


def test_conflict_can_be_quarantined_without_overwriting_old_fact() -> None:
    repo = InMemoryMarketDataRepository(duplicate_policy=DuplicatePolicy.CONFLICT_TO_QUARANTINE)
    first = bar()
    conflicting = replace(first, close_price=Decimal("10.11"))

    assert repo.save_bar(first) == "inserted"
    assert repo.save_bar(conflicting) == "quarantined"
    stored = repo.read_bars(
        symbol="000001",
        from_time=utc("2026-07-03T01:31:00+00:00"),
        to_time=utc("2026-07-03T01:31:00+00:00"),
        timeframe="1m",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )

    assert stored == [first]
    assert repo.quarantine_records[0].reason_code == "VERSION_CONFLICT"


def test_replay_reads_standardized_bars_in_market_time_order() -> None:
    repo = InMemoryMarketDataRepository()
    later = bar(time="2026-07-03T01:32:00+00:00")
    earlier = bar(time="2026-07-03T01:31:00+00:00")
    repo.save_bar(later)
    repo.save_bar(earlier)

    replayed = list(
        MarketDataReplaySource(repo).read(
            symbol="000001",
            from_time=utc("2026-07-03T01:31:00+00:00"),
            to_time=utc("2026-07-03T01:32:00+00:00"),
            timeframe="1m",
            data_source_version="akshare-exploration-v1",
            as_of_version="asof-research-v1",
        )
    )

    assert [item.market_data_time for item in replayed] == [
        utc("2026-07-03T01:31:00+00:00"),
        utc("2026-07-03T01:32:00+00:00"),
    ]


def test_reconciler_reports_provider_mismatches_without_silent_fixing() -> None:
    ak_bar = bar(close="10.10", source="AKShare", version="akshare-exploration-v1")
    ts_bar = bar(close="10.11", source="Tushare", version="tushare-research-v1")

    report = MarketDataReconciler().compare_bars(
        left_provider="AKShare",
        right_provider="Tushare",
        left=[ak_bar],
        right=[ts_bar],
        price_tolerance=Decimal("0"),
    )

    assert not report.is_clean
    assert report.compared_count == 1
    assert report.issues[0].issue_type == "CLOSE_PRICE_MISMATCH"

