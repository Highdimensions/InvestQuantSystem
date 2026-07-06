"""Fuzz tests for BacktestRunSpec parsing.

These tests construct random YAML payloads and assert that the loader
either parses them into a ``BacktestRunSpec`` or raises a
``BacktestRunSpecValidationError``.  They MUST NOT crash the loader.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from quant_signal_system.backtest.run_spec import (
    BacktestRunSpecLoader,
    BacktestRunSpecValidationError,
)


def _random_spec(seed: int, *, valid: bool) -> str:
    import random

    rng = random.Random(seed)
    binders = []
    n_bindings = 1 if valid else rng.choice([0, 1])
    for i in range(n_bindings):
        binders.append(f"""
  - binding_id: "b{i}"
    strategy_name: {"'rule_vol_breakout'" if valid else "''"}
    strategy_version: "v{i}"
    parameter_hash: "ph{i}"
    universe_id: "u{i}"
    universe_version: "v{i}"
    feature_version: "f{i}"
""")
    if valid:
        from_time = "2025-06-02T09:30:00+00:00"
        to_time = "2025-06-02T10:00:00+00:00"
    else:
        from_time = rng.choice(["not-a-date", "2025-13-99T99:99:99"])
        to_time = "2025-06-02T10:00:00+00:00"
    return f"""
from_time: "{from_time}"
to_time: "{to_time}"
timeframe: "1m"
data_source_version: "dv1"
as_of_version: "asof-v1"
strategy_bindings:
{''.join(binders)}
"""


def _write_yaml(parent: Path, text: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    p = parent / "spec.yaml"
    p.write_text(text, encoding="utf-8")
    return p


class TestRunSpecFuzz:
    def test_random_valid_specs_parse(self, tmp_path: Path) -> None:
        for seed in range(20):
            yaml_text = _random_spec(seed, valid=True)
            spec_path = _write_yaml(tmp_path / f"s{seed}", yaml_text)
            spec = BacktestRunSpecLoader.from_yaml(spec_path)
            assert spec.strategy_bindings
            assert spec.from_time < spec.to_time

    def test_random_invalid_specs_raise_cleanly(self, tmp_path: Path) -> None:
        for seed in range(20):
            yaml_text = _random_spec(seed, valid=False)
            spec_path = _write_yaml(tmp_path / f"s{seed}", yaml_text)
            with pytest.raises(BacktestRunSpecValidationError):
                BacktestRunSpecLoader.from_yaml(spec_path)

    def test_garbage_does_not_crash(self, tmp_path: Path) -> None:
        garbage = [
            "%YAML 1.1\n--- invalid: [\n",
            "[unclosed",
            "  : : :",
            "" ,
            "from_time: 1\nto_time: 0\n",
        ]
        for i, text in enumerate(garbage):
            p = _write_yaml(tmp_path / f"g{i}", text)
            try:
                BacktestRunSpecLoader.from_yaml(p)
            except BacktestRunSpecValidationError:
                pass
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"loader raised unexpected exception {exc!r} for input {text!r}")
