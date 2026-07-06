"""Tests for backtest/run_spec.py."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.backtest.run_spec import (
    BacktestRunSpec,
    BacktestRunSpecLoader,
    BacktestRunSpecValidationError,
    StrategyBinding,
)
from quant_signal_system.contracts.market import MarketDataValidationError


class TestStrategyBinding:
    def test_valid_binding(self) -> None:
        b = StrategyBinding(
            binding_id="vol_breakout_hs300_v1",
            strategy_name="volume_breakout",
            strategy_version="v1",
            parameter_hash="abc123",
            universe_id="hs300",
            universe_version="v20250701",
            feature_version="rolling-feature-v1",
        )
        b.validate()
        assert b.binding_id == "vol_breakout_hs300_v1"
        assert b.weight == Decimal("1.0")
        assert b.composer_policy == "PRIORITY_MAX_CONFIDENCE"

    def test_missing_binding_id_raises(self) -> None:
        b = StrategyBinding(
            binding_id="",
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="h",
            universe_id="u",
            universe_version="v1",
            feature_version="f1",
        )
        with pytest.raises(MarketDataValidationError, match="binding_id"):
            b.validate()

    def test_negative_weight_raises(self) -> None:
        b = StrategyBinding(
            binding_id="b1",
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="h",
            universe_id="u",
            universe_version="v1",
            feature_version="f1",
            weight=Decimal("-1"),
        )
        with pytest.raises(MarketDataValidationError, match="weight"):
            b.validate()

    def test_valid_from_after_valid_to_raises(self) -> None:
        b = StrategyBinding(
            binding_id="b1",
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="h",
            universe_id="u",
            universe_version="v1",
            feature_version="f1",
            valid_from=datetime(2025, 7, 1, tzinfo=timezone.utc),
            valid_to=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(MarketDataValidationError, match="valid_from"):
            b.validate()


class TestBacktestRunSpec:
    def test_valid_spec(self) -> None:
        spec = BacktestRunSpec(
            run_id="run_001",
            from_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            to_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
            strategy_bindings=(
                StrategyBinding(
                    binding_id="b1",
                    strategy_name="x",
                    strategy_version="v1",
                    parameter_hash="h",
                    universe_id="u",
                    universe_version="v1",
                    feature_version="f1",
                ),
            ),
        )
        assert spec.run_mode == "backtest"
        assert spec.timeframe == "1m"
        assert len(spec.strategy_bindings) == 1

    def test_from_time_after_to_time_raises(self) -> None:
        with pytest.raises(MarketDataValidationError, match="from_time must be before"):
            BacktestRunSpec(
                from_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                to_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                strategy_bindings=(
                    StrategyBinding(
                        binding_id="b1",
                        strategy_name="x",
                        strategy_version="v1",
                        parameter_hash="h",
                        universe_id="u",
                        universe_version="v1",
                        feature_version="f1",
                    ),
                ),
            )

    def test_empty_bindings_raises(self) -> None:
        with pytest.raises(MarketDataValidationError, match="at least one strategy_binding"):
            BacktestRunSpec(
                from_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                to_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                strategy_bindings=(),
            )

    def test_unknown_timeframe_raises(self) -> None:
        with pytest.raises(MarketDataValidationError, match="unknown timeframe"):
            BacktestRunSpec(
                from_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
                to_time=datetime(2025, 12, 31, tzinfo=timezone.utc),
                timeframe="99d",
                strategy_bindings=(
                    StrategyBinding(
                        binding_id="b1",
                        strategy_name="x",
                        strategy_version="v1",
                        parameter_hash="h",
                        universe_id="u",
                        universe_version="v1",
                        feature_version="f1",
                    ),
                ),
            )

    def test_resolved_hash_deterministic(self) -> None:
        t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 12, 31, tzinfo=timezone.utc)
        spec1 = BacktestRunSpec(
            from_time=t1,
            to_time=t2,
            strategy_bindings=(
                StrategyBinding(
                    binding_id="b1",
                    strategy_name="x",
                    strategy_version="v1",
                    parameter_hash="abc",
                    universe_id="u",
                    universe_version="v1",
                    feature_version="f1",
                ),
            ),
        )
        spec2 = BacktestRunSpec(
            from_time=t1,
            to_time=t2,
            strategy_bindings=(
                StrategyBinding(
                    binding_id="b1",
                    strategy_name="x",
                    strategy_version="v1",
                    parameter_hash="abc",
                    universe_id="u",
                    universe_version="v1",
                    feature_version="f1",
                ),
            ),
        )
        assert spec1.compute_resolved_hash() == spec2.compute_resolved_hash()

    def test_resolved_hash_changes_with_params(self) -> None:
        t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2025, 12, 31, tzinfo=timezone.utc)
        spec1 = BacktestRunSpec(
            from_time=t1, to_time=t2,
            strategy_bindings=(
                StrategyBinding(
                    binding_id="b1",
                    strategy_name="x",
                    strategy_version="v1",
                    parameter_hash="abc",
                    universe_id="u",
                    universe_version="v1",
                    feature_version="f1",
                ),
            ),
        )
        spec2 = BacktestRunSpec(
            from_time=t1, to_time=t2,
            strategy_bindings=(
                StrategyBinding(
                    binding_id="b1",
                    strategy_name="x",
                    strategy_version="v1",
                    parameter_hash="def",  # changed
                    universe_id="u",
                    universe_version="v1",
                    feature_version="f1",
                ),
            ),
        )
        assert spec1.compute_resolved_hash() != spec2.compute_resolved_hash()


class TestBacktestRunSpecLoader:
    def test_from_dict_minimal(self) -> None:
        data = {
            "from_time": "2025-01-01T00:00:00Z",
            "to_time": "2025-12-31T00:00:00Z",
            "strategy_bindings": [
                {
                    "binding_id": "b1",
                    "strategy_name": "x",
                    "strategy_version": "v1",
                    "parameter_hash": "h",
                    "universe_id": "u",
                    "universe_version": "v1",
                    "feature_version": "f1",
                }
            ],
        }
        spec = BacktestRunSpecLoader.from_dict(data)
        assert spec.from_time == datetime(2025, 1, 1, tzinfo=timezone.utc)
        assert len(spec.strategy_bindings) == 1
        assert spec.strategy_bindings[0].binding_id == "b1"

    def test_missing_required_field_raises(self) -> None:
        data = {
            "from_time": "2025-01-01T00:00:00Z",
            "to_time": "2025-12-31T00:00:00Z",
            "strategy_bindings": [
                {
                    # missing binding_id
                    "strategy_name": "x",
                    "strategy_version": "v1",
                    "parameter_hash": "h",
                    "universe_id": "u",
                    "universe_version": "v1",
                    "feature_version": "f1",
                }
            ],
        }
        with pytest.raises(BacktestRunSpecValidationError):
            BacktestRunSpecLoader.from_dict(data)

    def test_datetime_formats(self) -> None:
        # ISO with Z suffix
        data1 = {
            "from_time": "2025-01-01T00:00:00Z",
            "to_time": "2025-12-31T00:00:00Z",
            "strategy_bindings": [
                {
                    "binding_id": "b1",
                    "strategy_name": "x",
                    "strategy_version": "v1",
                    "parameter_hash": "h",
                    "universe_id": "u",
                    "universe_version": "v1",
                    "feature_version": "f1",
                }
            ],
        }
        spec1 = BacktestRunSpecLoader.from_dict(data1)
        assert spec1.from_time.tzinfo == timezone.utc

    def test_invalid_datetime_raises(self) -> None:
        data = {
            "from_time": "not-a-date",
            "to_time": "2025-12-31T00:00:00Z",
            "strategy_bindings": [
                {
                    "binding_id": "b1",
                    "strategy_name": "x",
                    "strategy_version": "v1",
                    "parameter_hash": "h",
                    "universe_id": "u",
                    "universe_version": "v1",
                    "feature_version": "f1",
                }
            ],
        }
        with pytest.raises(BacktestRunSpecValidationError, match="datetime"):
            BacktestRunSpecLoader.from_dict(data)
