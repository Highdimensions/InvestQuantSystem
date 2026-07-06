"""Tests for backtest/manifest.py."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from quant_signal_system.backtest.manifest import (
    ArtifactRef,
    AssertionResult,
    BacktestRunManifest,
    ManifestBuilder,
    RunWarning,
)
from quant_signal_system.contracts.market import MarketDataValidationError


class TestRunWarning:
    def test_basic(self) -> None:
        w = RunWarning(
            warning_code="MISSING_BAR",
            severity="warn",
            message="bar missing between 2025-06-01 and 2025-06-03",
            affected_symbols=("300346",),
        )
        assert w.warning_code == "MISSING_BAR"
        assert w.count == 1

    def test_serialization_roundtrip(self) -> None:
        w = RunWarning(
            warning_code="DATA_INTERRUPTION",
            severity="error",
            message="3 bars missing",
            affected_symbols=("300346", "600519"),
            count=3,
        )
        d = dataclasses.asdict(w)
        assert d["schema_version"] == "run-warning-v1"
        assert d["warning_code"] == "DATA_INTERRUPTION"


class TestArtifactRef:
    def test_basic(self) -> None:
        a = ArtifactRef(
            artifact_name="signals.json",
            artifact_path="signals.json",
            artifact_type="json",
            record_count=42,
        )
        assert a.artifact_name == "signals.json"
        assert a.record_count == 42


class TestBacktestRunManifest:
    def test_minimal_manifest(self) -> None:
        m = BacktestRunManifest(
            run_id="run_001",
            run_mode="backtest",
            run_status="success",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        m.validate()
        assert m.run_id == "run_001"
        assert m.run_status == "success"

    def test_unknown_status_raises(self) -> None:
        m = BacktestRunManifest(
            run_id="run_001",
            run_mode="backtest",
            run_status="unknown",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(MarketDataValidationError, match="run_status"):
            m.validate()

    def test_empty_run_id_raises(self) -> None:
        m = BacktestRunManifest(
            run_id="",
            run_mode="backtest",
            run_status="success",
            created_at=datetime(2025, 7, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(MarketDataValidationError, match="run_id"):
            m.validate()

    def test_serialization_roundtrip(self) -> None:
        m = BacktestRunManifest(
            run_id="run_001",
            run_mode="backtest",
            run_status="success",
            created_at=datetime(2025, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
            total_signals_generated=10,
            total_bars_processed=100,
            warnings=(
                RunWarning(
                    warning_code="MISSING_BAR",
                    severity="warn",
                    message="1 bar missing",
                    count=1,
                ),
            ),
        )
        m.validate()
        m.to_json()  # ensure no exception
        d = m.to_dict()
        assert "run_id" in d
        assert d["total_signals_generated"] == 10


class TestManifestBuilder:
    def test_minimal_builder(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        m = builder.finalize("success")
        assert m.run_id == "run_001"
        assert m.run_status == "success"
        assert m.completed_at is not None

    def test_empty_run_id_raises(self) -> None:
        with pytest.raises(ValueError, match="run_id"):
            ManifestBuilder(run_id="")

    def test_add_warning(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        builder.add_warning(
            RunWarning(warning_code="MISSING_BAR", severity="warn", message="test")
        )
        builder.add_warning(
            RunWarning(warning_code="DATA_INTERRUPTION", severity="error", message="test2", count=3)
        )
        m = builder.finalize("partial")
        assert len(m.warnings) == 2
        assert m.warnings[1].count == 3

    def test_set_versions(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        builder.set_versions(
            strategy_versions=("v1", "v2"),
            universe_versions=("u1",),
            data_source_version="akshare-v1",
            as_of_version="asof-v1",
        )
        m = builder.finalize("success")
        assert m.strategy_versions == ("v1", "v2")
        assert m.universe_versions == ("u1",)
        assert m.data_source_version == "akshare-v1"

    def test_add_assertion(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        builder.add_assertion(
            AssertionResult(assertion_name="determinism", passed=True, detail="all consistent")
        )
        m = builder.finalize("success")
        assert len(m.assertion_results) == 1
        assert m.assertion_results[0].passed is True
        assert "determinism" in m.expected_assertions

    def test_deterministic_check(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        builder.set_deterministic_check(passed=True, detail="2 runs matched")
        m = builder.finalize("success")
        assert m.deterministic_check_passed is True
        assert m.deterministic_check_detail == "2 runs matched"

    def test_config_snapshot(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        builder.set_config_snapshot(
            original_spec_yaml="run_mode: backtest\n",
            resolved_config_hash="abc123def456",
        )
        m = builder.finalize("success")
        assert m.original_spec_yaml == "run_mode: backtest\n"
        assert m.resolved_config_hash == "abc123def456"

    def test_statistics(self) -> None:
        builder = ManifestBuilder(run_id="run_001")
        builder.set_statistics(
            total_bars_processed=1000,
            total_signals_generated=50,
            total_fills=45,
            total_evaluations_completed=50,
        )
        m = builder.finalize("success")
        assert m.total_bars_processed == 1000
        assert m.total_signals_generated == 50
        assert m.total_fills == 45

    def test_data_range(self) -> None:
        from_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        to_time = datetime(2025, 12, 31, tzinfo=timezone.utc)
        builder = ManifestBuilder(run_id="run_001")
        builder.set_data_range(from_time=from_time, to_time=to_time, timeframe="1d")
        m = builder.finalize("success")
        assert m.from_time == from_time
        assert m.to_time == to_time
        assert m.timeframe == "1d"
