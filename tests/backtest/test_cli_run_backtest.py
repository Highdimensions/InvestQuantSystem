"""Tests for the run_backtest CLI command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_signal_system.cli.run_backtest import cli as run_backtest_cli


def _spec_yaml(path: Path, *, output_dir: Path) -> None:
    """Write a minimal valid spec YAML."""
    yaml_text = f"""
from_time: "2025-06-02T09:30:00+00:00"
to_time: "2025-06-02T10:00:00+00:00"
timeframe: "1m"
data_source_version: "dv1"
as_of_version: "asof-v1"
market_rule_version: "rule-v1"
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


class TestRunBacktestCLI:
    def test_missing_spec_returns_user_error(self, tmp_path: Path) -> None:
        exit_code = run_backtest_cli(["--spec", str(tmp_path / "missing.yaml")])
        assert exit_code == 1

    def test_invalid_spec_returns_user_error(self, tmp_path: Path) -> None:
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("not_a_valid_spec: true\n", encoding="utf-8")
        exit_code = run_backtest_cli(["--spec", str(spec_path)])
        assert exit_code == 1

    def test_runs_and_writes_manifest(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        exit_code = run_backtest_cli(["--spec", str(spec_path)])
        assert exit_code == 0
        manifest_path = output_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["run_status"] == "success"
        assert manifest["from_time"].startswith("2025-06-02T09:30:00")

    def test_debug_writes_event_trace(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        exit_code = run_backtest_cli(["--spec", str(spec_path), "--debug"])
        assert exit_code == 0
        events_path = output_dir / "debug" / "events.jsonl"
        assert events_path.exists()
        lines = events_path.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "debug trace should have at least one event"
        first = json.loads(lines[0])
        assert first["event"] == "run_complete"

    def test_resume_skips_re_run_when_manifest_matches(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        spec_path = tmp_path / "spec.yaml"
        _spec_yaml(spec_path, output_dir=output_dir)
        first = run_backtest_cli(["--spec", str(spec_path)])
        assert first == 0
        second = run_backtest_cli(["--spec", str(spec_path), "--resume"])
        assert second == 0