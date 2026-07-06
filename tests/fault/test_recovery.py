"""Fault tests: mid-run failure recovery, partial persistence, duplicate tasks, data interruption."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant_signal_system.cli._common import load_manifest
from quant_signal_system.cli.run_backtest import cli as run_backtest_cli
from quant_signal_system.cli.validate_backtest import validate as validate_manifest


def _spec_yaml(path: Path, *, output_dir: Path) -> None:
    yaml_text = f"""
from_time: "2025-06-02T09:30:00+00:00"
to_time: "2025-06-02T10:00:00+00:00"
timeframe: "1m"
data_source_version: "dv1"
as_of_version: "asof-v1"
output_dir: "{output_dir.as_posix()}"
strategy_bindings:
  - binding_id: "b1"
    strategy_name: "rule_vol_breakout"
    strategy_version: "v1"
    parameter_hash: "ph1"
    universe_id: "u1"
    universe_version: "v1"
    feature_version: "f1"
"""
    path.write_text(yaml_text, encoding="utf-8")


class TestMidRunFailure:
    def test_resume_detects_existing_manifest(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        first = run_backtest_cli(["--spec", str(spec_path)])
        assert first == 0
        second = run_backtest_cli(["--spec", str(spec_path), "--resume"])
        assert second == 0

    def test_resume_with_changed_spec_returns_failed(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        first = run_backtest_cli(["--spec", str(spec_path)])
        assert first == 0
        # Change spec data_source_version -> resolved_config_hash differs.
        spec_text = spec_path.read_text(encoding="utf-8")
        spec_path.write_text(spec_text.replace("dv1", "dv2"), encoding="utf-8")
        second = run_backtest_cli(["--spec", str(spec_path), "--resume"])
        assert second == 2


class TestPartialPersistence:
    def test_manifest_present_and_valid_after_run(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        run_backtest_cli(["--spec", str(spec_path)])
        ok, errors = validate_manifest(output_dir)
        assert ok is True
        assert errors == []


class TestDuplicateTaskExecution:
    def test_signal_idempotent_under_resume(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        run_backtest_cli(["--spec", str(spec_path)])
        # Second run with resume should not produce duplicate artifacts.
        run_backtest_cli(["--spec", str(spec_path), "--resume"])
        manifest = load_manifest(output_dir / "manifest.json")
        # No duplicates allowed; artifact list should remain consistent.
        names = [a.artifact_name for a in manifest.artifacts]
        assert len(names) == len(set(names))


class TestDataInterruption:
    def test_empty_data_run_succeeds_with_zero_signals(self, tmp_path: Path) -> None:
        """When no bars are available, the run should still complete with zero signals."""
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        code = run_backtest_cli(["--spec", str(spec_path)])
        assert code == 0
        manifest = load_manifest(output_dir / "manifest.json")
        assert manifest.total_signals_generated == 0
        assert manifest.run_status == "success"