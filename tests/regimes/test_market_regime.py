"""Tests for the market regime engine."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quant_signal_system.regimes import (
    MarketRegimeEngine,
    RegimeConfig,
    RegimeLabel,
)


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class TestRegimeConfig:
    def test_default_config(self) -> None:
        cfg = RegimeConfig()
        assert cfg.high_vol_threshold == 0.01
        assert cfg.trend_threshold == 0.015

    def test_version_is_stable(self) -> None:
        cfg = RegimeConfig()
        v1 = cfg.regime_config_version()
        v2 = cfg.regime_config_version()
        assert v1 == v2

    def test_version_changes_on_threshold(self) -> None:
        cfg1 = RegimeConfig()
        cfg2 = RegimeConfig(high_vol_threshold=0.02)
        assert cfg1.regime_config_version() != cfg2.regime_config_version()


class TestMarketRegimeEngine:
    def test_range(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={"return_window": 0.005, "return_stddev": 0.005, "volume_ratio": 1.0},
        )
        assert out.label == RegimeLabel.RANGE

    def test_trend(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={
                "return_window": 0.02,
                "return_stddev": 0.005,
                "volume_ratio": 1.0,  # below breakout threshold
            },
        )
        assert out.label == RegimeLabel.TREND

    def test_breakout(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={
                "return_window": 0.02,
                "return_stddev": 0.005,
                "volume_ratio": 2.0,  # above breakout threshold
            },
        )
        assert out.label == RegimeLabel.BREAKOUT

    def test_high_volatility(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={
                "return_window": 0.005,
                "return_stddev": 0.05,
                "volume_ratio": 1.0,
            },
        )
        assert out.label == RegimeLabel.HIGH_VOLATILITY

    def test_risk_avoid(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={"return_window": 0.0, "return_stddev": 0.0, "volume_ratio": 1.0},
            signal_confidence=0.05,
        )
        assert out.label == RegimeLabel.RISK_AVOID

    def test_risk_avoid_overrides_high_volatility(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={
                "return_window": 0.05,
                "return_stddev": 0.10,
                "volume_ratio": 2.0,
            },
            signal_confidence=0.10,
        )
        assert out.label == RegimeLabel.RISK_AVOID

    def test_classified_regime_is_risk_avoid(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={},
            signal_confidence=0.0,
        )
        assert out.is_risk_avoid()

    def test_to_dict(self) -> None:
        engine = MarketRegimeEngine()
        out = engine.classify(
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:30:00+00:00"),
            features={"return_window": 0.0, "return_stddev": 0.0, "volume_ratio": 1.0},
        )
        d = out.to_dict()
        assert d["symbol"] == "300346"
        assert d["label"] == RegimeLabel.RANGE.value