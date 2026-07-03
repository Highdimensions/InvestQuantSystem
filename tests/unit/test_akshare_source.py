from datetime import datetime, timezone
from decimal import Decimal

from quant_signal_system.config.data_source import akshare_exploration_profile
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.market_data.akshare_source import AKShareMarketDataSource
from quant_signal_system.market_data.quarantine import QuarantineRecord


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class FakeFrame:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, *, orient):
        assert orient == "records"
        return self.rows


class FakeAKShare:
    def __init__(self):
        self.minute_calls = []
        self.daily_calls = []

    def stock_zh_a_hist_min_em(self, **kwargs):
        self.minute_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "时间": "2024-07-03 09:31:00",
                    "开盘": "10.00",
                    "收盘": "10.10",
                    "最高": "10.20",
                    "最低": "9.90",
                    "成交量": "10000",
                    "成交额": "101000",
                }
            ]
        )

    def stock_zh_a_hist(self, **kwargs):
        self.daily_calls.append(kwargs)
        return FakeFrame(
            [
                {
                    "日期": "2024-07-03",
                    "股票代码": "000001",
                    "开盘": "10.00",
                    "收盘": "10.10",
                    "最高": "10.20",
                    "最低": "9.90",
                    "成交量": "10000",
                    "成交额": "101000",
                    "换手率": "0.30",
                }
            ]
        )


def test_akshare_minute_source_fetches_and_normalizes_closed_bars() -> None:
    client = FakeAKShare()
    source = AKShareMarketDataSource(akshare_client=client)

    bars = list(
        source.read(
            symbols=["000001.SZ"],
            from_time=utc("2024-07-03T01:30:00+00:00"),
            to_time=utc("2024-07-03T01:32:00+00:00"),
        )
    )

    assert len(bars) == 1
    bar = bars[0]
    assert isinstance(bar, MarketBar)
    assert bar.symbol == "000001"
    assert bar.market_data_time == utc("2024-07-03T01:31:00+00:00")
    assert bar.close_price == Decimal("10.10")
    assert bar.source == "AKShare"
    assert client.minute_calls[0]["symbol"] == "000001"
    assert client.minute_calls[0]["period"] == "1"


def test_akshare_daily_source_uses_market_close_time_for_date_rows() -> None:
    client = FakeAKShare()
    source = AKShareMarketDataSource(
        akshare_client=client,
        profile=akshare_exploration_profile(frequency="1d"),
    )

    bars = list(
        source.read(
            symbols=["000001"],
            from_time=utc("2024-07-03T00:00:00+00:00"),
            to_time=utc("2024-07-03T08:00:00+00:00"),
        )
    )

    assert len(bars) == 1
    assert bars[0].market_data_time == utc("2024-07-03T07:00:00+00:00")
    assert client.daily_calls[0]["period"] == "daily"


def test_akshare_source_can_surface_quarantine_records_for_bad_rows() -> None:
    class BadAKShare(FakeAKShare):
        def stock_zh_a_hist_min_em(self, **kwargs):
            return FakeFrame([{"时间": "2024-07-03 09:31:00", "开盘": "10.00"}])

    source = AKShareMarketDataSource(akshare_client=BadAKShare())

    results = list(
        source.read_with_quarantine(
            symbols=["000001"],
            from_time=utc("2024-07-03T01:30:00+00:00"),
            to_time=utc("2024-07-03T01:32:00+00:00"),
        )
    )

    assert len(results) == 1
    assert isinstance(results[0], QuarantineRecord)
    assert results[0].reason_code == "NORMALIZATION_FAILED"
