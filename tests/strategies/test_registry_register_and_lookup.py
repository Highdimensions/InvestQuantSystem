"""Tests for the Phase B strategy registry and freeze governance."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_signal_system.config.versions import (
    DuplicateStrategyFreezeError,
    VersionRegistry,
)
from quant_signal_system.contracts.features import FeatureSnapshot
from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.contracts.signals import (
    Direction,
    ExposureEffect,
    SignalAction,
    SignalCandidate,
)
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies import (
    DEFAULT_REGISTRY,
    DuplicateStrategyError,
    RuleStrategyRuntime,
    SchemaError,
    StrategyRegistry,
    UnknownStrategyError,
)
from quant_signal_system.strategies.metadata import StrategySpec
from quant_signal_system.strategies.protocol import StrategyRuntime
from quant_signal_system.strategies.schema import compute_parameter_hash
from quant_signal_system.time.clock import FrozenClock


def _make_feature_snapshot() -> FeatureSnapshot:
    from datetime import datetime, timezone

    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap-1",
        symbol="000001",
        market_data_time=datetime(2024, 7, 3, 1, 33, tzinfo=timezone.utc),
        generated_at=datetime(2024, 7, 3, 1, 33, tzinfo=timezone.utc),
        feature_version="rolling-feature-v1",
        lookback_window="3bars",
        features={"close": 10.30},
        missing_data_flags=(),
        input_bar_range="2024-07-03T01:31:00..2024-07-03T01:33:00",
    )


def _make_candidate(runtime: StrategyRuntime) -> SignalCandidate:
    from datetime import datetime, timezone
    from decimal import Decimal

    return SignalCandidate(
        symbol="000001",
        direction=Direction.BUY,
        signal_action=SignalAction.BUY,
        exposure_effect=ExposureEffect.INCREASE_LONG,
        market_data_time=datetime(2024, 7, 3, 1, 33, tzinfo=timezone.utc),
        reference_price=Decimal("10.30"),
        score=Decimal("0.70"),
        confidence=Decimal("0.60"),
        horizon_seconds=runtime.horizon_seconds,
        reason_codes=("VOLUME_BREAKOUT",),
        invalid_condition=None,
        feature_snapshot=_make_feature_snapshot(),
        market_regime=None,
        strategy_name=runtime.name,
        strategy_version=runtime.version,
        feature_version="rolling-feature-v1",
        code_version=runtime.code_version,
        parameter_hash=runtime.parameter_hash,
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def test_version_registry_freeze_strategy_is_idempotent() -> None:
    registry = VersionRegistry()
    first = registry.freeze_strategy(
        strategy_name="baseline",
        strategy_version="v1",
        parameter_hash="hash-1",
        code_version="code-1",
    )
    second = registry.freeze_strategy(
        strategy_name="baseline",
        strategy_version="v1",
        parameter_hash="hash-1",
        code_version="code-1",
    )
    assert first == second
    assert registry.is_strategy_frozen(
        strategy_name="baseline",
        strategy_version="v1",
        parameter_hash="hash-1",
        code_version="code-1",
    )


def test_version_registry_freeze_strategy_rejects_conflicting_identity() -> None:
    registry = VersionRegistry()
    registry.freeze_strategy(
        strategy_name="baseline",
        strategy_version="v1",
        parameter_hash="hash-1",
        code_version="code-1",
    )
    with pytest.raises(DuplicateStrategyFreezeError):
        registry.freeze_strategy(
            strategy_name="baseline",
            strategy_version="v1",
            parameter_hash="hash-2",
            code_version="code-1",
        )


def test_version_registry_frozen_strategies_lists_all() -> None:
    registry = VersionRegistry()
    registry.freeze_strategy(
        strategy_name="a",
        strategy_version="v1",
        parameter_hash="h1",
        code_version="c1",
    )
    registry.freeze_strategy(
        strategy_name="b",
        strategy_version="v2",
        parameter_hash="h2",
        code_version="c2",
    )
    names = {item.strategy_name for item in registry.frozen_strategies()}
    assert names == {"a", "b"}


def test_strategy_registry_registers_rule_strategy_with_defaults() -> None:
    registry = StrategyRegistry()
    spec = registry.register(RuleStrategyRuntime)
    assert spec.name == "baseline-rules"
    assert spec.version == "baseline-rules-v1"
    assert spec.parameter_hash == RuleStrategyRuntime().parameter_hash
    assert registry.names() == ("baseline-rules",)
    assert registry.get("baseline-rules").name == "baseline-rules"


def test_strategy_registry_register_is_idempotent() -> None:
    registry = StrategyRegistry()
    spec_a = registry.register(RuleStrategyRuntime)
    spec_b = registry.register(RuleStrategyRuntime)
    assert spec_a == spec_b


def test_strategy_registry_register_with_yaml_path(tmp_path: Path) -> None:
    yaml_path = tmp_path / "params.yaml"
    yaml_path.write_text("breakout_volume_ratio: 2.0\n", encoding="utf-8")

    registry = StrategyRegistry()
    spec = registry.register(RuleStrategyRuntime, yaml_path=yaml_path)
    expected_hash = compute_parameter_hash(
        {
            "breakout_volume_ratio": 2.0,
            "pullback_threshold": -0.01,
            "spike_threshold": 0.02,
            "horizon_seconds": 900,
        }
    )
    assert spec.parameter_hash == expected_hash


def test_strategy_registry_register_with_inline_params() -> None:
    registry = StrategyRegistry()
    spec = registry.register(
        RuleStrategyRuntime,
        params={"breakout_volume_ratio": 2.5, "horizon_seconds": 1800},
    )
    expected_hash = compute_parameter_hash(
        {
            "breakout_volume_ratio": 2.5,
            "pullback_threshold": -0.01,
            "spike_threshold": 0.02,
            "horizon_seconds": 1800,
        }
    )
    assert spec.parameter_hash == expected_hash


def test_strategy_registry_rejects_unknown_yaml_field(tmp_path: Path) -> None:
    yaml_path = tmp_path / "params.yaml"
    yaml_path.write_text("unknown_field: 1\n", encoding="utf-8")

    registry = StrategyRegistry()
    with pytest.raises(SchemaError, match="unknown parameter"):
        registry.register(RuleStrategyRuntime, yaml_path=yaml_path)


def test_strategy_registry_rejects_duplicate_strategy_with_different_identity() -> None:
    registry = StrategyRegistry()
    registry.register(RuleStrategyRuntime)
    with pytest.raises(DuplicateStrategyError):
        registry.register(RuleStrategyRuntime, params={"breakout_volume_ratio": 2.0})


def test_strategy_registry_rejects_duplicate_yaml_and_params() -> None:
    registry = StrategyRegistry()
    with pytest.raises(MarketDataValidationError, match="only one"):
        registry.register(
            RuleStrategyRuntime,
            params={"breakout_volume_ratio": 2.0},
            yaml_path=Path("ignored.yaml"),
        )


def test_strategy_registry_rejects_class_without_protocol() -> None:
    class NotAStrategy:
        pass

    registry = StrategyRegistry()
    with pytest.raises(MarketDataValidationError, match="does not satisfy"):
        registry.register(NotAStrategy)


def test_strategy_registry_unknown_lookup_raises() -> None:
    registry = StrategyRegistry()
    with pytest.raises(UnknownStrategyError, match="not registered"):
        registry.get("ghost")


def test_strategy_registry_resolve_many_returns_in_order() -> None:
    registry = StrategyRegistry()
    registry.register(RuleStrategyRuntime)
    runtime = registry.resolve_many(("baseline-rules",))[0]
    assert isinstance(runtime, RuleStrategyRuntime)


def test_default_registry_is_singleton() -> None:
    from quant_signal_system.strategies import DEFAULT_REGISTRY as a
    from quant_signal_system.strategies import DEFAULT_REGISTRY as b

    assert a is b


def test_strategy_registry_frozen_in_version_registry() -> None:
    version_registry = VersionRegistry()
    registry = StrategyRegistry(version_registry=version_registry)
    registry.register(RuleStrategyRuntime)
    assert version_registry.is_strategy_frozen(
        strategy_name="baseline-rules",
        strategy_version="baseline-rules-v1",
        parameter_hash=RuleStrategyRuntime().parameter_hash,
        code_version="research-code-v1",
    )


def test_strategy_spec_validation_requires_required_fields() -> None:
    spec = StrategySpec(name="", version="v1", code_version="c", parameter_hash="p", horizon_seconds=1, yaml_path=None)
    with pytest.raises(MarketDataValidationError):
        spec.validate()


def test_signal_service_rejects_unfrozen_strategy() -> None:
    clock = FrozenClock(__import__("datetime").datetime(2024, 7, 3, 1, 35, tzinfo=__import__("datetime").timezone.utc))
    version_registry = VersionRegistry()
    service = SignalService(clock=clock, version_registry=version_registry)
    runtime = RuleStrategyRuntime()
    candidate = _make_candidate(runtime)

    with pytest.raises(MarketDataValidationError, match="not frozen"):
        service.create_event(candidate)


def test_signal_service_accepts_frozen_strategy() -> None:
    clock = FrozenClock(__import__("datetime").datetime(2024, 7, 3, 1, 35, tzinfo=__import__("datetime").timezone.utc))
    version_registry = VersionRegistry()
    runtime = RuleStrategyRuntime()
    version_registry.freeze_strategy(
        strategy_name=runtime.name,
        strategy_version=runtime.version,
        parameter_hash=runtime.parameter_hash,
        code_version=runtime.code_version,
    )

    service = SignalService(clock=clock, version_registry=version_registry)
    candidate = _make_candidate(runtime)
    event = service.create_event(candidate)
    assert event.signal_id.startswith(runtime.parameter_hash[:8]) or len(event.signal_id) == 32


def test_signal_service_without_registry_still_accepts_candidate() -> None:
    clock = FrozenClock(__import__("datetime").datetime(2024, 7, 3, 1, 35, tzinfo=__import__("datetime").timezone.utc))
    service = SignalService(clock=clock)
    runtime = RuleStrategyRuntime()
    candidate = _make_candidate(runtime)
    event = service.create_event(candidate)
    assert event.strategy_name == "baseline-rules"


def test_default_registry_can_be_used_for_registration() -> None:
    DEFAULT_REGISTRY.register(RuleStrategyRuntime)
    assert DEFAULT_REGISTRY.get("baseline-rules").name == "baseline-rules"