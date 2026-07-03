from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.config.data_source import (
    akshare_exploration_profile,
    tushare_research_profile,
)
from quant_signal_system.contracts.market import MarketBar, MarketDataValidationError, TradingStatus
from quant_signal_system.contracts.reference_data import AsOfDataset
from quant_signal_system.market_data.normalizer import (
    AKSHARE_A_SHARE_FIELD_MAP,
    BarNormalizer,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def test_akshare_row_is_normalized_to_internal_closed_market_bar() -> None:
    profile = akshare_exploration_profile()
    row = {
        "股票代码": "000001",
        "时间": "2026-07-03T01:31:00+00:00",
        "开盘": "10.00",
        "最高": "10.20",
        "最低": "9.90",
        "收盘": "10.10",
        "成交量": "10000",
        "成交额": "101000",
        "换手率": "0.3",
        "交易状态": "交易",
    }

    bar = BarNormalizer().normalize_raw_bar(
        row,
        profile=profile,
        field_map=AKSHARE_A_SHARE_FIELD_MAP,
        ingest_time=utc("2026-07-03T01:31:02+00:00"),
    )

    assert bar.symbol == "000001"
    assert bar.timeframe == "1m"
    assert bar.market_data_time == utc("2026-07-03T01:31:00+00:00")
    assert bar.close_price == Decimal("10.10")
    assert bar.data_source_version == "akshare-exploration-v1"
    assert bar.as_of_version == "asof-research-v1"
    assert bar.source == "AKShare"
    assert bar.trading_status == TradingStatus.TRADING


def test_unclosed_bar_is_rejected_before_feature_or_strategy_use() -> None:
    bar = MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=utc("2026-07-03T01:30:00+00:00"),
        bar_end_time=utc("2026-07-03T01:31:00+00:00"),
        market_data_time=utc("2026-07-03T01:31:00+00:00"),
        ingest_time=utc("2026-07-03T01:30:30+00:00"),
        open_price=Decimal("10.00"),
        high_price=Decimal("10.20"),
        low_price=Decimal("9.90"),
        close_price=Decimal("10.10"),
        volume=Decimal("10000"),
        amount=Decimal("101000"),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=False,
        bar_close_time=utc("2026-07-03T01:31:00+00:00"),
        source="AKShare",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )

    with pytest.raises(MarketDataValidationError, match="only closed"):
        bar.validate(require_closed=True)


def test_normalizer_quarantines_provider_field_changes() -> None:
    profile = tushare_research_profile()
    row = {"ts_code": "000001.SZ", "trade_time": "2026-07-03T01:31:00+00:00"}

    result = BarNormalizer().quarantine_raw_bar(
        row,
        profile=profile,
        field_map=AKSHARE_A_SHARE_FIELD_MAP,
        ingest_time=utc("2026-07-03T01:31:02+00:00"),
    )

    assert result.__class__.__name__ == "QuarantineRecord"
    assert result.reason_code == "NORMALIZATION_FAILED"
    assert result.data_source_version == "tushare-research-v1"


def test_reference_data_must_be_visible_at_decision_time() -> None:
    dataset = AsOfDataset(
        schema_version="asof-dataset-v1",
        dataset="industry_membership",
        key="000001",
        effective_time=utc("2026-07-01T00:00:00+00:00"),
        available_at=utc("2026-07-04T00:00:00+00:00"),
        revision_id="rev-20260704",
        as_of_version="asof-research-v1",
        payload={"industry": "bank"},
    )

    with pytest.raises(MarketDataValidationError, match="not visible"):
        dataset.validate_visible_at(utc("2026-07-03T01:31:00+00:00"))

