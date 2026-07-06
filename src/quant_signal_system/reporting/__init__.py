"""Reports and shadow-run reconciliation."""

from quant_signal_system.reporting.artifacts import write_json, write_manifest, write_report
from quant_signal_system.reporting.dimensions import ReportDimensions, SignalMetricsDimensions
from quant_signal_system.reporting.reconciliation import ShadowRunComparator
from quant_signal_system.reporting.report_builder import ArtifactReportBuilder, ReportInput
from quant_signal_system.reporting.reports import (
    BacktestReport,
    BacktestReportBuilder,
    EvaluationReport,
    EvaluationReportBuilder,
)
from quant_signal_system.reporting.tables import markdown_table

__all__ = [
    "ArtifactReportBuilder",
    "BacktestReport",
    "BacktestReportBuilder",
    "EvaluationReport",
    "EvaluationReportBuilder",
    "ReportDimensions",
    "ReportInput",
    "ShadowRunComparator",
    "SignalMetricsDimensions",
    "markdown_table",
    "write_json",
    "write_manifest",
    "write_report",
]
