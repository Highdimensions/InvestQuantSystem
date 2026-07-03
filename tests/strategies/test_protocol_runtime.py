"""Tests for the Phase A strategy plugin primitives.

Covers:

* `StrategyRuntime` Protocol structural conformance
* `ParamSchema` validation, defaults, and freeze hashing
* `load_params` for YAML/JSON/inline/mapping inputs
* `RuleStrategyRuntime.from_params` backward compatibility
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from quant_signal_system.strategies import (
    ParamField,
    ParamSchema,
    RuleStrategyRuntime,
    SchemaError,
    StrategyRuntime,
    compute_parameter_hash,
    load_params,
)


def test_rule_strategy_runtime_satisfies_protocol() -> None:
    runtime = RuleStrategyRuntime()
    assert isinstance(runtime, StrategyRuntime)
    assert runtime.name == "baseline-rules"
    assert runtime.version == "baseline-rules-v1"
    assert runtime.code_version == "research-code-v1"
    assert runtime.horizon_seconds == 900
    params = dict(runtime.declare_parameters())
    assert params["breakout_volume_ratio"] == 1.5
    assert params["horizon_seconds"] == 900


def test_param_schema_applies_defaults_for_missing_fields() -> None:
    schema = ParamSchema.of(
        ("lookback", int, 20),
        ("z_entry", float, 1.5),
    )
    assert schema.validate({}) == {"lookback": 20, "z_entry": 1.5}


def test_param_schema_rejects_unknown_fields() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    with pytest.raises(SchemaError, match="unknown parameter"):
        schema.validate({"lookback": 10, "extras": 1})


def test_param_schema_coerces_strings_to_declared_types() -> None:
    schema = ParamSchema.of(("lookback", int, 20), ("z_entry", float, 1.5))
    resolved = schema.validate({"lookback": "10", "z_entry": "1.75"})
    assert resolved == {"lookback": 10, "z_entry": 1.75}


def test_param_schema_rejects_incompatible_types() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    with pytest.raises(SchemaError, match="cannot be coerced"):
        schema.validate({"lookback": "abc"})


def test_param_schema_rejects_duplicate_field_names() -> None:
    with pytest.raises(SchemaError, match="unique"):
        ParamSchema.of(
            ParamField("lookback", int, 10),
            ParamField("lookback", int, 20),
        )


def test_compute_parameter_hash_is_stable_and_order_independent() -> None:
    schema = ParamSchema.of(("a", int, 1), ("b", int, 2))
    resolved = schema.validate({"b": 2, "a": 1})
    assert compute_parameter_hash(resolved) == compute_parameter_hash({"a": 1, "b": 2})


def test_compute_parameter_hash_changes_when_value_changes() -> None:
    schema = ParamSchema.of(("a", int, 1))
    assert compute_parameter_hash(schema.validate({"a": 1})) != compute_parameter_hash(
        schema.validate({"a": 2})
    )


def test_load_params_from_mapping() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    loaded = load_params({"lookback": 10}, schema)
    assert dict(loaded.params) == {"lookback": 10}
    assert loaded.parameter_hash == compute_parameter_hash({"lookback": 10})
    assert loaded.source == "<inline-mapping>"


def test_load_params_from_inline_json_string() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    payload = json.dumps({"lookback": 10})
    loaded = load_params(payload, schema)
    assert dict(loaded.params) == {"lookback": 10}
    assert loaded.source == "<inline-json>"


def test_load_params_from_yaml_file(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    yaml_path = tmp_path / "params.yaml"
    yaml_path.write_text("lookback: 10\nz_entry: 1.75\n", encoding="utf-8")
    schema = ParamSchema.of(("lookback", int, 20), ("z_entry", float, 1.5))
    loaded = load_params(yaml_path, schema)
    assert dict(loaded.params) == {"lookback": 10, "z_entry": 1.75}
    assert loaded.source == f"yaml:{yaml_path}"
    assert loaded.parameter_hash == compute_parameter_hash({"lookback": 10, "z_entry": 1.75})


def test_load_params_yaml_failure_falls_back_to_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    fake_yaml = types.ModuleType("yaml")
    fake_yaml.safe_load = lambda _text: {"lookback": 99}
    monkeypatch.setitem(sys.modules, "yaml", fake_yaml)

    yaml_path = tmp_path / "ok.yaml"
    yaml_path.write_text("lookback: 99\n", encoding="utf-8")
    loaded = load_params(yaml_path, schema)
    assert dict(loaded.params) == {"lookback": 99}


def test_load_params_unknown_field_raises_schema_error() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    with pytest.raises(SchemaError, match="unknown parameter"):
        load_params({"lookback": 10, "extra": 1}, schema)


def test_load_params_inline_json_invalid_raises() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    with pytest.raises(SchemaError, match="inline JSON parameter payload is invalid"):
        load_params("{not-json", schema)


def test_load_params_inline_json_must_be_mapping() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    with pytest.raises(SchemaError, match="must be a mapping"):
        load_params('[1, 2, 3]', schema)


def test_load_params_path_does_not_exist_raises() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    with pytest.raises(SchemaError, match="does not exist"):
        load_params("definitely/not/a/file.yaml", schema)


def test_load_params_empty_string_yields_defaults() -> None:
    schema = ParamSchema.of(("lookback", int, 20))
    loaded = load_params("", schema)
    assert dict(loaded.params) == {"lookback": 20}


def test_rule_strategy_from_params_uses_declared_defaults() -> None:
    runtime = RuleStrategyRuntime.from_params({})
    assert runtime.breakout_volume_ratio == 1.5
    assert runtime.parameter_hash == compute_parameter_hash(
        {
            "breakout_volume_ratio": 1.5,
            "pullback_threshold": -0.01,
            "spike_threshold": 0.02,
            "horizon_seconds": 900,
        }
    )


def test_rule_strategy_from_params_recomputes_hash_on_change() -> None:
    runtime = RuleStrategyRuntime.from_params({"breakout_volume_ratio": 2.0})
    assert runtime.parameter_hash != RuleStrategyRuntime().parameter_hash
    assert runtime.breakout_volume_ratio == 2.0


def test_rule_strategy_from_params_rejects_unknown_field() -> None:
    with pytest.raises(SchemaError, match="unknown parameter"):
        RuleStrategyRuntime.from_params({"bogus": 1})


def test_minimal_strategy_runtime_structural_conformance() -> None:
    """Any dataclass exposing the protocol surface should pass `isinstance`."""

    @dataclass(frozen=True, slots=True)
    class MinimalRuntime:
        strategy_name: str = "minimal"
        strategy_version: str = "minimal-v1"
        code_version: str = "research-code-v1"
        horizon_seconds: int = 900

        @property
        def name(self) -> str:
            return self.strategy_name

        @property
        def version(self) -> str:
            return self.strategy_version

        @property
        def parameter_hash(self) -> str:
            return "minimal-hash"

        def declare_parameters(self) -> tuple[tuple[str, object], ...]:
            return (("horizon_seconds", self.horizon_seconds),)

        def on_bar(self, bar, snapshot, regime=None):  # type: ignore[no-untyped-def]
            return None

    assert isinstance(MinimalRuntime(), StrategyRuntime)