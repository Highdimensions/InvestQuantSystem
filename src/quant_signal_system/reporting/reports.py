"""Batch research reports that expose sample states and versions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from quant_signal_system.contracts.evaluation import SignalEvaluation
from quant_signal_system.evaluation.metrics import PortfolioMetrics, SignalMetrics


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


@dataclass(frozen=True, slots=True)
class BacktestReport:
    """Full backtest report."""
    run_id: str
    from_time: str
    to_time: str
    signal_count: int
    fill_count: int
    evaluation_count: int
    unexecutable_count: int
    portfolio_metrics: PortfolioMetrics | None
    signal_metrics: list[SignalMetrics]
    warnings: list[str]

    def to_markdown(self) -> str:
        lines = [
            f"# Backtest Report: {self.run_id}",
            "",
            "## Summary",
            "",
            f"- run_id: {self.run_id}",
            f"- from_time: {self.from_time}",
            f"- to_time: {self.to_time}",
            f"- signal_count: {self.signal_count}",
            f"- fill_count: {self.fill_count}",
            f"- evaluation_count: {self.evaluation_count}",
            f"- unexecutable_count: {self.unexecutable_count}",
        ]
        if self.portfolio_metrics:
            pm = self.portfolio_metrics
            lines += [
                "",
                "## Portfolio Metrics",
                "",
                f"- initial_cash: {pm.initial_cash}",
                f"- final_value: {pm.final_value}",
                f"- total_return: {pm.total_return}",
                f"- annualized_return: {pm.annualized_return}",
                f"- sharpe_ratio: {pm.sharpe_ratio}",
                f"- max_drawdown: {pm.max_drawdown}",
                f"- calmar_ratio: {pm.calmar_ratio}",
                f"- trade_count: {pm.trade_count}",
                f"- days: {pm.days}",
            ]
        if self.signal_metrics:
            lines += [
                "",
                "## Signal Metrics by Bucket",
                "",
            ]
            for sm in self.signal_metrics:
                lines.append(
                    f"- {sm.strategy_name} | {sm.symbol} | dir={sm.direction} | "
                    f"win_rate={sm.win_rate:.2%} | avg_net={sm.avg_net_return:.4f}"
                )
        if self.warnings:
            lines += [
                "",
                "## Warnings",
                "",
            ]
            for w in self.warnings:
                lines.append(f"- {w}")
        return "\n".join(lines)


class BacktestReportBuilder:
    def build(
        self,
        run_id: str,
        from_time: str,
        to_time: str,
        signal_count: int,
        fill_count: int,
        evaluation_count: int,
        unexecutable_count: int,
        portfolio_metrics: PortfolioMetrics | None,
        signal_metrics: list[SignalMetrics],
        warnings: list[str],
    ) -> BacktestReport:
        return BacktestReport(
            run_id=run_id,
            from_time=from_time,
            to_time=to_time,
            signal_count=signal_count,
            fill_count=fill_count,
            evaluation_count=evaluation_count,
            unexecutable_count=unexecutable_count,
            portfolio_metrics=portfolio_metrics,
            signal_metrics=signal_metrics,
            warnings=warnings,
        )
