"""Top-level report builder that writes the artifact bundle.

Aggregates signal and portfolio metrics and serialises them to the artifact
set required by Phase 5:

- ``manifest.json``
- ``signals.parquet`` (JSONL fallback)
- ``fills.parquet`` (JSONL fallback)
- ``evaluations.parquet`` (JSONL fallback)
- ``report.md``
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from quant_signal_system.contracts.evaluation import SignalEvaluation
from quant_signal_system.contracts.signals import SignalEvent
from quant_signal_system.contracts.portfolio import PaperFill
from quant_signal_system.evaluation.metrics import PortfolioMetrics, SignalMetrics
from quant_signal_system.reporting.artifacts import write_manifest, write_parquet_fallback, write_report
from quant_signal_system.reporting.reports import BacktestReport, BacktestReportBuilder


@dataclass(frozen=True, slots=True)
class ReportInput:
    run_id: str
    from_time: datetime
    to_time: datetime
    signals: tuple[SignalEvent, ...]
    fills: tuple[PaperFill, ...]
    evaluations: tuple[SignalEvaluation, ...]
    signal_metrics: tuple[SignalMetrics, ...]
    portfolio_metrics: PortfolioMetrics | None
    warnings: tuple[str, ...]

    def signal_count(self) -> int:
        return len(self.signals)

    def fill_count(self) -> int:
        return len(self.fills)

    def evaluation_count(self) -> int:
        return len(self.evaluations)

    def unexecutable_count(self) -> int:
        return sum(1 for e in self.evaluations if e.net_return is None)


def _to_dict(obj: object) -> object:
    if is_dataclass(obj):
        d = dataclasses.asdict(obj)
        return {k: _to_dict(v) if is_dataclass(v) else v for k, v in d.items()}
    return obj


class ArtifactReportBuilder:
    """Builds the standard Phase 5 artifact bundle on disk."""

    def __init__(self, builder: BacktestReportBuilder | None = None) -> None:
        self._builder = builder or BacktestReportBuilder()

    def write(
        self,
        output_dir: Path,
        report_input: ReportInput,
        manifest_extra: Mapping[str, object] | None = None,
    ) -> BacktestReport:
        output_dir.mkdir(parents=True, exist_ok=True)

        write_parquet_fallback(output_dir / "signals.parquet", [_to_dict(s) for s in report_input.signals])
        write_parquet_fallback(output_dir / "fills.parquet", [_to_dict(f) for f in report_input.fills])
        write_parquet_fallback(
            output_dir / "evaluations.parquet",
            [_to_dict(e) for e in report_input.evaluations],
        )

        manifest = {
            "run_id": report_input.run_id,
            "from_time": report_input.from_time.isoformat(),
            "to_time": report_input.to_time.isoformat(),
            "signal_count": report_input.signal_count(),
            "fill_count": report_input.fill_count(),
            "evaluation_count": report_input.evaluation_count(),
            "unexecutable_count": report_input.unexecutable_count(),
            "warnings": list(report_input.warnings),
        }
        if report_input.portfolio_metrics is not None:
            manifest["portfolio_metrics"] = _to_dict(report_input.portfolio_metrics)
        if manifest_extra:
            for key, value in manifest_extra.items():
                manifest[key] = _to_dict(value) if is_dataclass(value) else value
        write_manifest(output_dir / "manifest.json", manifest)

        report = self._builder.build(
            run_id=report_input.run_id,
            from_time=report_input.from_time.isoformat(),
            to_time=report_input.to_time.isoformat(),
            signal_count=report_input.signal_count(),
            fill_count=report_input.fill_count(),
            evaluation_count=report_input.evaluation_count(),
            unexecutable_count=report_input.unexecutable_count(),
            portfolio_metrics=report_input.portfolio_metrics,
            signal_metrics=list(report_input.signal_metrics),
            warnings=list(report_input.warnings),
        )
        write_report(output_dir / "report.md", report.to_markdown())
        return report
