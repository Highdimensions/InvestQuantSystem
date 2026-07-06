"""Tests for the artifact report builder."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from quant_signal_system.contracts.evaluation import (
    BarrierConflictPolicy,
    EvaluationTaskStatus,
    PathGranularity,
    SignalEvaluation,
)
from quant_signal_system.evaluation.metrics import PortfolioMetrics, SignalMetrics
from quant_signal_system.reporting.report_builder import ArtifactReportBuilder, ReportInput


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _evaluation(signal_id: str = "s1") -> SignalEvaluation:
    return SignalEvaluation(
        schema_version="signal-evaluation-v1",
        evaluation_run_id="e1",
        signal_id=signal_id,
        horizon_seconds=900,
        evaluation_time=_utc("2025-06-02T09:32:00+00:00"),
        executable_time=_utc("2025-06-02T09:32:00+00:00"),
        executable_price=Decimal("42"),
        executable_price_source="next_bar_open",
        execution_status=__import__("quant_signal_system.contracts.signals", fromlist=["ExecutionStatus"]).ExecutionStatus.EXECUTABLE,
        unexecutable_reason=None,
        evaluation_price=Decimal("42.5"),
        raw_return=Decimal("0.01"),
        direction_return=Decimal("0.01"),
        net_return=Decimal("0.01"),
        mfe=Decimal("0.02"),
        mae=Decimal("-0.005"),
        time_to_mfe_seconds=None,
        time_to_mae_seconds=None,
        triple_barrier_label=None,
        barrier_config_version="barrier-v1",
        path_granularity=PathGranularity.BAR_OHLC,
        barrier_conflict_policy=BarrierConflictPolicy.AMBIGUOUS,
        transaction_cost=Decimal("0"),
        slippage=Decimal("0"),
        spread_cost=Decimal("0"),
        signal_delay_seconds=0,
        evaluator_version="signal-evaluator-v1",
        evaluation_policy_version="policy-v1",
        cost_model_version="cost-v1",
        slippage_model_version="slip-v1",
        delay_model_version="delay-v1",
        fill_model_version="fill-v1",
        data_source_version="dv1",
        as_of_version="asof-v1",
        created_at=_utc("2025-06-02T09:32:00+00:00"),
        status=EvaluationTaskStatus.COMPLETED,
    )


def _sm() -> SignalMetrics:
    return SignalMetrics(
        strategy_name="rule_vol_breakout",
        strategy_version="v1",
        symbol="300346",
        direction=1,
        reason_code="TEST_REASON",
        year=2025,
        month=6,
        sample_count=10,
        unexecutable_count=1,
        win_count=6,
        loss_count=3,
        avg_net_return=Decimal("0.005"),
        std_net_return=Decimal("0.01"),
        avg_mfe=Decimal("0.02"),
        avg_mae=Decimal("-0.005"),
        mfe_mae_ratio=Decimal("4"),
    )


def _pm() -> PortfolioMetrics:
    return PortfolioMetrics(
        initial_cash=Decimal("1000000"),
        final_value=Decimal("1100000"),
        total_return=Decimal("0.1"),
        annualized_return=Decimal("0.05"),
        sharpe_ratio=Decimal("1.5"),
        max_drawdown=Decimal("0.05"),
        calmar_ratio=Decimal("2.0"),
        turnover=Decimal("0.3"),
        trade_count=10,
        days=252,
    )


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    return tmp_path / "backtest_output"


class TestArtifactReportBuilder:
    def test_writes_all_artifacts(self, output_dir: Path) -> None:
        from quant_signal_system.contracts.signals import SignalEvent, Direction, SignalAction, ExposureEffect, ExecutionStatus
        from quant_signal_system.contracts.features import FeatureSnapshot

        snapshot = FeatureSnapshot(
            schema_version="feature-snapshot-v1",
            feature_snapshot_id="snap-1",
            symbol="300346",
            market_data_time=_utc("2025-06-02T09:31:00+00:00"),
            generated_at=_utc("2025-06-02T09:31:00+00:00"),
            feature_version="f1",
            lookback_window="3bars",
            features={"close": 42.0},
            missing_data_flags=(),
            input_bar_range="2025-06-02T09:29:00..2025-06-02T09:31:00",
        )
        signal = SignalEvent(
            schema_version="signal-event-v1",
            signal_id="s1",
            symbol="300346",
            direction=Direction.BUY,
            signal_action=SignalAction.BUY,
            exposure_effect=ExposureEffect.INCREASE_LONG,
            event_time=_utc("2025-06-02T09:31:00+00:00"),
            market_data_time=_utc("2025-06-02T09:31:00+00:00"),
            ingest_time=_utc("2025-06-02T09:31:00+00:00"),
            executable_time=_utc("2025-06-02T09:32:00+00:00"),
            reference_price=Decimal("42"),
            executable_price=None,
            executable_price_source=None,
            execution_status=ExecutionStatus.UNKNOWN_AT_EVENT_TIME,
            unexecutable_reason=None,
            score=Decimal("0.7"),
            confidence=Decimal("0.6"),
            horizon_seconds=900,
            reason_codes=("R",),
            invalid_condition=None,
            feature_snapshot=snapshot,
            market_regime=None,
            strategy_name="rule_vol_breakout",
            strategy_version="v1",
            feature_version="f1",
            code_version="cv1",
            parameter_hash="h",
            data_source_version="dv1",
            as_of_version="asof-v1",
            created_at=_utc("2025-06-02T09:31:00+00:00"),
        )

        report_input = ReportInput(
            run_id="run-1",
            from_time=_utc("2025-06-01T00:00:00+00:00"),
            to_time=_utc("2025-06-30T23:59:00+00:00"),
            signals=(signal,),
            fills=(),
            evaluations=(_evaluation(),),
            signal_metrics=(_sm(),),
            portfolio_metrics=_pm(),
            warnings=(),
        )
        builder = ArtifactReportBuilder()
        report = builder.write(output_dir, report_input)
        assert output_dir.exists()
        assert (output_dir / "manifest.json").exists()
        assert (output_dir / "signals.parquet").exists()
        assert (output_dir / "fills.parquet").exists()
        assert (output_dir / "evaluations.parquet").exists()
        assert (output_dir / "report.md").exists()
        assert report.run_id == "run-1"
        manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["run_id"] == "run-1"
        assert manifest["signal_count"] == 1
        assert "portfolio_metrics" in manifest


class TestMarkdownTable:
    def test_simple_table(self) -> None:
        from quant_signal_system.reporting.tables import markdown_table

        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        columns = ["a", "b"]
        result = markdown_table(rows, columns)
        assert "| a | b |" in result
        assert "| 1 | 2 |" in result
        assert "| 3 | 4 |" in result
