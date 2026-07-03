"""Batch research reports that expose sample states and versions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from quant_signal_system.contracts.evaluation import SignalEvaluation


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    total: int
    status_counts: dict[str, int]
    version_counts: dict[str, int]

    def to_markdown(self) -> str:
        lines = [
            "# Signal Evaluation Report",
            "",
            "本报告仅用于研究和系统正确性检查，不构成收益承诺。",
            "",
            f"- total: {self.total}",
            f"- status_counts: {self.status_counts}",
            f"- version_counts: {self.version_counts}",
        ]
        return "\n".join(lines)


class EvaluationReportBuilder:
    def build(self, evaluations: list[SignalEvaluation]) -> EvaluationReport:
        return EvaluationReport(
            total=len(evaluations),
            status_counts=dict(Counter(item.status.value for item in evaluations)),
            version_counts=dict(Counter(item.evaluation_policy_version for item in evaluations)),
        )

