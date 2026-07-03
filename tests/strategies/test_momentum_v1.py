"""Tests for the example momentum strategy and YAML config."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from quant_signal_system.config.versions import VersionRegistry
from quant_signal_system.contracts.features import FeatureSnapshot
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies import (
    DEFAULT_REGISTRY,
    StrategyRegistry,
)
from quant_signal_system.strategies._examples.momentum_v1 import MomentumV1Strategy
from quant_signal_system.strategies.protocol import StrategyRuntime
from quant_signal_system.time.clock import FrozenClock


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _bar(close: str = "10.10") -> MarketBar:
    end = utc("2024-07-03T01:33:00+00:00")
    price = Decimal(close)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=end.replace(minute=end.minute - 1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=price,
        high_price=price + Decimal("0.10"),
        low_price=price - Decimal("0.10"),
        close_price=price,
        volume=Decimal("100"),
        amount=price * Decimal("100"),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source="AKShare",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def _snapshot(*, return_1: float = 0.01) -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap",
        symbol="000001",
        market_data_time=utc("2024-07-03T01:33:00+00:00"),
        generated_at=utc("2024-07-03T01:33:00+00:00"),
        feature_version="rolling-feature-v1",
        lookback_window="3bars",
        features={"return_1": return_1, "close": 10.10},
        missing_data_flags=(),
        input_bar_range="2024-07-03T01:31:00..2024-07-03T01:33:00",
    )


def test_momentum_strategy_satisfies_protocol() -> None:
    runtime = MomentumV1Strategy()
    assert isinstance(runtime, StrategyRuntime)
    assert runtime.name == "momentum-v1"


def test_momentum_strategy_emits_buy_when_return_above_threshold() -> None:
    runtime = MomentumV1Strategy()
    bar = _bar()
    candidate = runtime.on_bar(bar, _snapshot(return_1=0.01))
    assert candidate is not None
    assert candidate.direction.name == "BUY"
    assert "MOMENTUM_CONFIRMED" in candidate.reason_codes


def test_momentum_strategy_abstains_when_return_below_threshold() -> None:
    runtime = MomentumV1Strategy()
    candidate = runtime.on_bar(_bar(), _snapshot(return_1=0.001))
    assert candidate is None


def test_momentum_strategy_abstains_on_missing_data() -> None:
    runtime = MomentumV1Strategy()
    snapshot = FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap",
        symbol="000001",
        market_data_time=utc("2024-07-03T01:33:00+00:00"),
        generated_at=utc("2024-07-03T01:33:00+00:00"),
        feature_version="rolling-feature-v1",
        lookback_window="3bars",
        features={},
        missing_data_flags=("INSUFFICIENT_LOOKBACK",),
        input_bar_range="2024-07-03T01:31:00..2024-07-03T01:33:00",
    )
    assert runtime.on_bar(_bar(), snapshot) is None


def test_momentum_strategy_yaml_config_loads() -> None:
    yaml_path = Path(__file__).parents[2] / "src" / "quant_signal_system" / "strategies" / "_examples" / "momentum_v1.yaml"
    if not yaml_path.exists():
        pytest.skip("momentum_v1.yaml missing")
    registry = StrategyRegistry()
    spec = registry.register(MomentumV1Strategy, yaml_path=yaml_path)
    assert spec.name == "momentum-v1"
    assert spec.parameter_hash != MomentumV1Strategy().parameter_hash


def test_momentum_strategy_registration_freezes_identity() -> None:
    version_registry = VersionRegistry()
    registry = StrategyRegistry(version_registry=version_registry)
    registry.register(MomentumV1Strategy)
    runtime = registry.get("momentum-v1")
    assert version_registry.is_strategy_frozen(
        strategy_name=runtime.name,
        strategy_version=runtime.version,
        parameter_hash=runtime.parameter_hash,
        code_version=runtime.code_version,
    )


def test_momentum_strategy_signal_accepted_when_frozen() -> None:
    version_registry = VersionRegistry()
    registry = StrategyRegistry(version_registry=version_registry)
    registry.register(MomentumV1Strategy)
    runtime = registry.get("momentum-v1")
    candidate = runtime.on_bar(_bar(), _snapshot(return_1=0.01))
    assert candidate is not None
    service = SignalService(clock=FrozenClock(utc("2024-07-03T01:35:00+00:00")), version_registry=version_registry)
    event = service.create_event(candidate)
    assert event.strategy_name == "momentum-v1"


def test_default_registry_can_register_momentum_strategy() -> None:
    DEFAULT_REGISTRY.register(MomentumV1Strategy, params={"return_threshold": 0.01})
    runtime = DEFAULT_REGISTRY.get("momentum-v1")
    assert runtime.return_threshold == 0.01