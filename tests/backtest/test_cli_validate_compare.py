"""Tests for validate_backtest and compare_runs CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from quant_signal_system.cli.compare_runs import cli as compare_runs_cli
from quant_signal_system.cli.compare_runs import compare as compare_manifests
from quant_signal_system.cli.compare_runs import render_diff
from quant_signal_system.cli.validate_backtest import cli as validate_backtest_cli
from quant_signal_system.cli.validate_backtest import validate as validate_manifest
from quant_signal_system.cli.run_backtest import cli as run_backtest_cli


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


def _run_once(tmp_path: Path, run_id_label: str) -> Path:
    """Run the CLI once and return the output directory."""
    output_dir = tmp_path / run_id_label
    spec_path = tmp_path / f"spec_{run_id_label}.yaml"
    _spec_yaml(spec_path, output_dir=output_dir)
    code = run_backtest_cli(["--spec", str(spec_path)])
    assert code == 0
    return output_dir


class TestValidateBacktest:
    def test_valid_manifest(self, tmp_path: Path) -> None:
        out = _run_once(tmp_path, "run1")
        ok, errors = validate_manifest(out)
        assert ok is True
        assert errors == []

    def test_missing_manifest(self, tmp_path: Path) -> None:
        ok, errors = validate_manifest(tmp_path / "empty")
        assert ok is False
        assert any("manifest.json not found" in e for e in errors)

    def test_cli_valid(self, tmp_path: Path) -> None:
        out = _run_once(tmp_path, "r1")
        code = validate_backtest_cli(["--artifact-dir", str(out)])
        assert code == 0

    def test_cli_missing_artifact_dir(self) -> None:
        code = validate_backtest_cli([])
        assert code == 1


class TestCompareRuns:
    def test_identical_runs_no_diff(self, tmp_path: Path) -> None:
        a = _run_once(tmp_path, "a")
        b = _run_once(tmp_path, "b")
        from quant_signal_system.cli._common import load_manifest
        diff = compare_manifests(load_manifest(a / "manifest.json"), load_manifest(b / "manifest.json"))
        assert diff["differences"] == {}
        assert diff["comparable"] is True

    def test_different_versions_reported(self, tmp_path: Path) -> None:
        a = _run_once(tmp_path, "a")
        b_path = tmp_path / "b" / "manifest.json"
        b_path.parent.mkdir(parents=True, exist_ok=True)
        a_data = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
        a_data["data_source_version"] = "dv2"
        b_path.write_text(json.dumps(a_data, indent=2), encoding="utf-8")
        from quant_signal_system.cli._common import load_manifest
        diff = compare_manifests(load_manifest(a / "manifest.json"), load_manifest(b_path))
        assert "data_source_version" in diff["differences"]
        rendered = render_diff(diff)
        assert "data_source_version" in rendered

    def test_cli_missing_args(self) -> None:
        code = compare_runs_cli([])
        assert code == 1

    def test_cli_missing_manifest(self, tmp_path: Path) -> None:
        code = compare_runs_cli([
            "--run-id-a", "x",
            "--run-id-b", "y",
            "--artifact-dir", str(tmp_path),
        ])
        assert code == 3