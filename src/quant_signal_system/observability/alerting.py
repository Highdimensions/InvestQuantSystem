"""Alerting: rule evaluation and event routing.

Implements the P1/P2/P3 alert taxonomy defined in
``docs/architecture/backtest-observability.md`` Section 5.

**Important**: concrete threshold values are marked TBD pending Phase 7
benchmarking. The rule engine is fully wired but will not fire until
thresholds are populated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from quant_signal_system.observability.metrics_collector import (
    MetricsCollector,
    MetricLabels,
    get_metrics,
)


class AlertSeverity(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


# Sentinel value used for uninitialized thresholds.
TBD: float = float("nan")


@dataclass(frozen=True, slots=True)
class AlertRule:
    """A rule that fires when a metric satisfies a condition for a duration."""

    name: str
    metric: str
    condition: Literal[">", ">=", "<", "<=", "==", "!="] = ">"
    threshold: float = TBD
    severity: AlertSeverity = AlertSeverity.P3
    pause_interpretation: bool = False
    runbook: str = ""
    description: str = ""

    def is_tbd(self) -> bool:
        """Return True when the threshold has not been calibrated yet."""
        import math
        return math.isnan(self.threshold)


@dataclass(frozen=True, slots=True)
class AlertEvent:
    """A single alert that has fired."""

    schema_version: str = "alert-event-v1"
    alert_name: str = ""
    severity: AlertSeverity = AlertSeverity.P3
    metric: str = ""
    condition: str = ""
    threshold: float = 0.0
    observed_value: float = 0.0
    pause_interpretation: bool = False
    runbook: str = ""
    run_id: str = ""
    fired_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        def _serialize(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, (AlertSeverity,)):
                return str(obj.value)
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj
        return _serialize(
            {
                "schema_version": self.schema_version,
                "alert_name": self.alert_name,
                "severity": self.severity,
                "metric": self.metric,
                "condition": self.condition,
                "threshold": self.threshold,
                "observed_value": self.observed_value,
                "pause_interpretation": self.pause_interpretation,
                "runbook": self.runbook,
                "run_id": self.run_id,
                "fired_at": self.fired_at,
                "payload": self.payload,
            }
        )


class AlertEvaluator:
    """Evaluates :class:`AlertRule` instances against a :class:`MetricsCollector`."""

    # P1 rules defined in backtest-observability.md §5.1
    DEFAULT_RULES: tuple[AlertRule, ...] = (
        AlertRule(
            name="missing_bars_p1",
            metric="backtest_missing_bars_total",
            condition=">",
            threshold=TBD,
            severity=AlertSeverity.P1,
            pause_interpretation=True,
            runbook="docs/runbooks/debug-data-quality.md",
            description="Missing bars exceed calibrated threshold.",
        ),
        AlertRule(
            name="evaluation_backlog_p1",
            metric="backtest_evaluation_backlog",
            condition=">",
            threshold=TBD,
            severity=AlertSeverity.P1,
            pause_interpretation=True,
            runbook="docs/runbooks/recover-failed-backtest.md",
            description="Evaluation backlog growing beyond calibrated threshold.",
        ),
        AlertRule(
            name="determinism_violation_p1",
            metric="_determinism_violation",
            condition="==",
            threshold=0.0,
            severity=AlertSeverity.P1,
            pause_interpretation=True,
            runbook="docs/runbooks/debug-backtest-mismatch.md",
            description="A determinism violation was detected.",
        ),
        AlertRule(
            name="signal_persist_failure_p1",
            metric="backtest_signal_persist_failure_total",
            condition=">",
            threshold=0.0,
            severity=AlertSeverity.P1,
            pause_interpretation=True,
            runbook="docs/runbooks/debug-backtest-mismatch.md",
            description="Signal persistence failed.",
        ),
        AlertRule(
            name="quarantine_records_p2",
            metric="backtest_quarantine_record_total",
            condition=">",
            threshold=TBD,
            severity=AlertSeverity.P2,
            pause_interpretation=False,
            runbook="docs/runbooks/debug-data-quality.md",
            description="Quarantine record count exceeds threshold.",
        ),
        AlertRule(
            name="version_mismatch_p2",
            metric="_version_mismatch",
            condition=">",
            threshold=0.0,
            severity=AlertSeverity.P2,
            pause_interpretation=True,
            runbook="docs/runbooks/debug-data-quality.md",
            description="Version mismatch detected in run.",
        ),
        AlertRule(
            name="report_duration_p3",
            metric="backtest_report_duration_seconds",
            condition=">",
            threshold=TBD,
            severity=AlertSeverity.P3,
            pause_interpretation=False,
            runbook="docs/runbooks/analyze-backtest-report.md",
            description="Report generation duration exceeds threshold.",
        ),
        AlertRule(
            name="order_rejection_rate_p3",
            metric="backtest_orders_rejected_total",
            condition=">",
            threshold=TBD,
            severity=AlertSeverity.P3,
            pause_interpretation=False,
            runbook="docs/runbooks/debug-signal-quality.md",
            description="Order rejection rate exceeds threshold.",
        ),
    )

    def __init__(
        self,
        rules: tuple[AlertRule, ...] | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        self._rules = rules or self.DEFAULT_RULES
        self._metrics = metrics or get_metrics()
        self._fired: list[AlertEvent] = []

    def evaluate(self, run_id: str = "") -> list[AlertEvent]:
        """Evaluate all non-TBD rules and return fired alerts for this run."""
        fired: list[AlertEvent] = []
        for rule in self._rules:
            if rule.is_tbd():
                continue
            value = self._read_metric(rule.metric)
            if value is None:
                continue
            if self._matches(rule, value):
                event = AlertEvent(
                    alert_name=rule.name,
                    severity=rule.severity,
                    metric=rule.metric,
                    condition=rule.condition,
                    threshold=rule.threshold,
                    observed_value=value,
                    pause_interpretation=rule.pause_interpretation,
                    runbook=rule.runbook,
                    run_id=run_id,
                )
                fired.append(event)
                self._fired.append(event)
        return fired

    def _read_metric(self, metric: str) -> float | None:
        """Read a counter/gauge value from the collector.

        Returns None for internal synthetic metrics that are not in the collector.
        If the metric is not present under the default ``run_id=""`` labels, falls
        back to scanning all known label sets and summing the values so callers
        see aggregated counts regardless of how labels were applied.
        """
        if metric.startswith("_"):
            return None
        default_labels = MetricLabels(run_id="")
        # Try as gauge first (backlog, age, etc.)
        gv = self._metrics.gauge_value(metric, default_labels)
        if gv is not None:
            return gv
        # Fall back to counter (per-label)
        counter = self._metrics._counters.get(metric)
        if counter is None:
            return None
        if default_labels.key() in counter.samples:
            return counter.samples[default_labels.key()]
        # Aggregate across all label sets for this metric
        total = 0.0
        for value in counter.samples.values():
            total += float(value)
        return total

    def _matches(self, rule: AlertRule, value: float) -> bool:
        cond = rule.condition
        thr = rule.threshold
        if cond == ">":
            return value > thr
        if cond == ">=":
            return value >= thr
        if cond == "<":
            return value < thr
        if cond == "<=":
            return value <= thr
        if cond == "==":
            return value == thr
        if cond == "!=":
            return value != thr
        return False

    @property
    def fired_alerts(self) -> tuple[AlertEvent, ...]:
        return tuple(self._fired)

    def reset(self) -> None:
        self._fired.clear()


class AlertRouter:
    """Routes fired :class:`AlertEvent` objects to handlers.

    Provides the routing hooks defined in backtest-observability.md §5.2.
    """

    def __init__(self) -> None:
        self._handlers: dict[AlertSeverity, list[AlertHandler]] = {
            AlertSeverity.P1: [],
            AlertSeverity.P2: [],
            AlertSeverity.P3: [],
        }
        self._all_handlers: list[AlertHandler] = []

    def add_handler(
        self,
        handler: AlertHandler,
        *,
        severity: AlertSeverity | None = None,
    ) -> None:
        """Register a handler. If ``severity`` is given the handler only receives
        alerts of that severity; otherwise it receives all alerts."""
        if severity is not None:
            self._handlers[severity].append(handler)
        self._all_handlers.append(handler)

    def route(self, event: AlertEvent) -> None:
        """Dispatch ``event`` to all matching handlers."""
        for handler in self._handlers.get(event.severity, []):
            handler(event)
        for handler in self._all_handlers:
            handler(event)


AlertHandler = Any
"""Type alias for alert handlers: ``Callable[[AlertEvent], None]``."""