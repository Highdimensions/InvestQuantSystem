"""Tests for the supplementary example strategies."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.features import FeatureSnapshot
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.strategies._examples.rally_fade import RallyFadeStrategy
from quant_signal_system.strategies._examples.volume_pullback import VolumePullbackStrategy


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _bar(symbol: str = "300346", close: str = "42") -> MarketBar:
    ts = _utc("2025-06-02T09:30:00+00:00")
    price = Decimal(close)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol=symbol,
        timeframe="1m",
        bar_start_time=ts - __import__("datetime").timedelta(minutes=1),
        bar_end_time=ts,
        market_data_time=ts,
        ingest_time=ts,
        open_price=price,
        high_price=price,
        low_price=price,
        close_price=price,
        volume=Decimal("1000"),
        amount=None,
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=ts,
        source="test",
        data_source_version="akshare-v1",
        as_of_version="asof-v1",
    )


def _snapshot(features: dict) -> FeatureSnapshot:
    ts = _utc("2025-06-02T09:30:00+00:00")
    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap_001",
        symbol="300346",
        market_data_time=ts,
        generated_at=ts,
        feature_version="rolling-feature-v1",
        lookback_window="3bars",
        features=features,
        missing_data_flags=(),
        input_bar_range="2025-06-02T09:28:00..2025-06-02T09:30:00",
    )


class TestVolumePullbackStrategy:
    def test_default_name_and_version(self) -> None:
        s = VolumePullbackStrategy()
        assert s.name == "volume-pullback-v1"
        assert s.version == "volume-pullback-v1"

    def test_from_params_builds_strategy(self) -> None:
        s = VolumePullbackStrategy.from_params(
            {"lookback_bars": 3, "pullback_threshold": 0.02}
        )
        assert s.lookback_bars == 3
        assert s.pullback_threshold == 0.02
        # parameter_hash must differ from defaults
        assert s.parameter_hash != VolumePullbackStrategy().parameter_hash

    def test_emits_sell_when_pullback_and_low_volume(self) -> None:
        s = VolumePullbackStrategy()
        out = s.on_bar(
            bar=_bar(),
            snapshot=_snapshot({"return_window": -0.03, "volume_ratio": 0.7}),
            regime=None,
        )
        assert out is not None
        assert out.direction.value == -1

    def test_no_signal_when_volume_high(self) -> None:
        s = VolumePullbackStrategy()
        out = s.on_bar(
            bar=_bar(),
            snapshot=_snapshot({"return_window": -0.03, "volume_ratio": 1.5}),
            regime=None,
        )
        assert out is None

    def test_no_signal_when_pullback_small(self) -> None:
        s = VolumePullbackStrategy()
        out = s.on_bar(
            bar=_bar(),
            snapshot=_snapshot({"return_window": -0.005, "volume_ratio": 0.7}),
            regime=None,
        )
        assert out is None

    def test_skips_on_missing_data(self) -> None:
        ts = _utc("2025-06-02T09:30:00+00:00")
        snapshot = FeatureSnapshot(
            schema_version="feature-snapshot-v1",
            feature_snapshot_id="snap_x",
            symbol="300346",
            market_data_time=ts,
            generated_at=ts,
            feature_version="rolling-feature-v1",
            lookback_window="3bars",
            features={"return_window": -0.03, "volume_ratio": 0.7},
            missing_data_flags=("volume",),
            input_bar_range="2025-06-02T09:28:00..2025-06-02T09:30:00",
        )
        out = VolumePullbackStrategy().on_bar(bar=_bar(), snapshot=snapshot, regime=None)
        assert out is None


class TestRallyFadeStrategy:
    def test_default_name_and_version(self) -> None:
        s = RallyFadeStrategy()
        assert s.name == "rally-fade-v1"
        assert s.version == "rally-fade-v1"

    def test_from_params_builds_strategy(self) -> None:
        s = RallyFadeStrategy.from_params({"rally_threshold": 0.03})
        assert s.rally_threshold == 0.03

    def test_emits_sell_when_rally_fades(self) -> None:
        s = RallyFadeStrategy()
        out = s.on_bar(
            bar=_bar(),
            snapshot=_snapshot(
                {"rally_amplitude": 0.04, "rally_fade": True}
            ),
            regime=None,
        )
        assert out is not None
        assert out.direction.value == -1

    def test_no_signal_when_no_fade_flag(self) -> None:
        s = RallyFadeStrategy()
        out = s.on_bar(
            bar=_bar(),
            snapshot=_snapshot(
                {"rally_amplitude": 0.04, "rally_fade": False}
            ),
            regime=None,
        )
        assert out is None

    def test_no_signal_when_amplitude_small(self) -> None:
        s = RallyFadeStrategy()
        out = s.on_bar(
            bar=_bar(),
            snapshot=_snapshot(
                {"rally_amplitude": 0.005, "rally_fade": True}
            ),
            regime=None,
        )
        assert out is None