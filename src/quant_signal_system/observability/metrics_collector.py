"""Metrics collector: Counter / Gauge / Histogram primitives.

Implements the metric catalog defined in
``docs/architecture/backtest-observability.md`` Section 3 and
``docs/architecture/testing-and-evaluation.md`` Section 8.2. The collector
is process-local and deterministic so tests can assert on exact values.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterable


class MetricType(StrEnum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass(frozen=True, slots=True)
class MetricLabels:
    """Standard label set for a metric sample.

    All fields are optional and default to empty strings so that the label
    tuple size is stable for hashability regardless of which fields are set.
    """

    run_id: str = ""
    binding_id: str = ""
    symbol: str = ""
    timeframe: str = ""
    horizon: str = ""
    side: str = ""
    status: str = ""
    direction: str = ""
    reason: str = ""
    policy: str = ""
    decision: str = ""
    report_type: str = ""
    rejection_reason: str = ""
    limit_direction: str = ""
    portfolio_id: str = ""
    extra: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        for key in (
            "run_id",
            "binding_id",
            "symbol",
            "timeframe",
            "horizon",
            "side",
            "status",
            "direction",
            "reason",
            "policy",
            "decision",
            "report_type",
            "rejection_reason",
            "limit_direction",
            "portfolio_id",
        ):
            value = getattr(self, key)
            if value:
                payload[key] = value
        for key, value in self.extra:
            payload[key] = value
        return payload

    def key(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self.to_dict().items()))


@dataclass
class _MetricBase:
    name: str
    metric_type: MetricType
    description: str = ""
    samples: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)

    def reset(self) -> None:
        self.samples.clear()

    def value(self, labels: MetricLabels) -> float:
        return self.samples.get(labels.key(), 0.0)


@dataclass
class Counter(_MetricBase):
    """Monotonic counter: ``inc`` only adds."""

    def inc(self, labels: MetricLabels, value: float = 1.0) -> None:
        if value < 0:
            raise ValueError(f"Counter {self.name} cannot decrease")
        key = labels.key()
        self.samples[key] = self.samples.get(key, 0.0) + value


@dataclass
class Gauge(_MetricBase):
    """Gauge: ``set`` overwrites, ``inc`` / ``dec`` adjust."""

    def set(self, labels: MetricLabels, value: float) -> None:
        self.samples[labels.key()] = value

    def inc(self, labels: MetricLabels, value: float = 1.0) -> None:
        key = labels.key()
        self.samples[key] = self.samples.get(key, 0.0) + value

    def dec(self, labels: MetricLabels, value: float = 1.0) -> None:
        key = labels.key()
        self.samples[key] = self.samples.get(key, 0.0) - value


@dataclass
class Histogram(_MetricBase):
    """Histogram with configurable bucket boundaries (in seconds, ms, etc.).

    Stores the bucket counts plus sum / count. Buckets are inclusive of the
    right boundary (le <= x), matching Prometheus convention.
    """

    buckets: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

    def observe(self, labels: MetricLabels, value: float) -> None:
        key = labels.key()
        existing = self.samples.get(key)
        if existing is None:
            bucket_counts: dict[str, int] = {f"{b}": 0 for b in self.buckets}
            bucket_counts["+Inf"] = 0
            record: dict[str, Any] = {
                "count": 0,
                "sum": 0.0,
                "buckets": bucket_counts,
            }
        else:
            # Restore a fresh copy from the existing record.
            record = {
                "count": existing["count"],
                "sum": existing["sum"],
                "buckets": dict(existing["buckets"]),
            }
        record["count"] += 1
        record["sum"] += value
        placed = False
        for boundary in self.buckets:
            if value <= boundary:
                record["buckets"][f"{boundary}"] += 1
                placed = True
                break
        if not placed:
            record["buckets"]["+Inf"] += 1
        self.samples[key] = record


_METRIC_NAMES_BACKTEST = {
    # Processing
    "backtest_bars_processed_total": MetricType.COUNTER,
    "backtest_bars_skipped_total": MetricType.COUNTER,
    "backtest_duplicate_bars_total": MetricType.COUNTER,
    "backtest_out_of_order_bars_total": MetricType.COUNTER,
    "backtest_missing_bars_total": MetricType.COUNTER,
    # Signal
    "backtest_signals_generated_total": MetricType.COUNTER,
    "backtest_signals_rejected_total": MetricType.COUNTER,
    "backtest_conflicts_total": MetricType.COUNTER,
    "backtest_abstained_total": MetricType.COUNTER,
    # Execution
    "backtest_orders_total": MetricType.COUNTER,
    "backtest_orders_accepted_total": MetricType.COUNTER,
    "backtest_orders_rejected_total": MetricType.COUNTER,
    "backtest_fills_total": MetricType.COUNTER,
    "backtest_t_plus_1_blocked_total": MetricType.COUNTER,
    "backtest_limit_blocked_total": MetricType.COUNTER,
    "backtest_suspended_blocked_total": MetricType.COUNTER,
    # Evaluation
    "backtest_evaluations_completed_total": MetricType.COUNTER,
    "backtest_evaluations_postponed_total": MetricType.COUNTER,
    "backtest_evaluation_backlog": MetricType.GAUGE,
    "backtest_oldest_evaluation_age_seconds": MetricType.GAUGE,
    # Performance
    "backtest_report_duration_seconds": MetricType.HISTOGRAM,
    "backtest_total_runtime_seconds": MetricType.GAUGE,
    "backtest_peak_memory_mb": MetricType.GAUGE,
    "backtest_processed_per_second": MetricType.GAUGE,
}

_METRIC_DESCRIPTIONS = {
    "backtest_bars_processed_total": "Total bars processed by the backtest.",
    "backtest_bars_skipped_total": "Bars skipped due to data quality issues.",
    "backtest_duplicate_bars_total": "Duplicate bars detected and skipped.",
    "backtest_out_of_order_bars_total": "Out-of-order bars detected.",
    "backtest_missing_bars_total": "Missing bars detected (gaps).",
    "backtest_signals_generated_total": "Signals generated.",
    "backtest_signals_rejected_total": "Signals rejected.",
    "backtest_conflicts_total": "Composer conflicts detected.",
    "backtest_abstained_total": "Strategies abstained from emitting a signal.",
    "backtest_orders_total": "Orders generated.",
    "backtest_orders_accepted_total": "Orders accepted by market rules.",
    "backtest_orders_rejected_total": "Orders rejected by market rules.",
    "backtest_fills_total": "Paper fills generated.",
    "backtest_t_plus_1_blocked_total": "T+1 sell blocks.",
    "backtest_limit_blocked_total": "Limit up/down blocks.",
    "backtest_suspended_blocked_total": "Suspended-symbol blocks.",
    "backtest_evaluations_completed_total": "Signal evaluations completed.",
    "backtest_evaluations_postponed_total": "Evaluations postponed due to missing data.",
    "backtest_evaluation_backlog": "Outstanding evaluation tasks.",
    "backtest_oldest_evaluation_age_seconds": "Age of the oldest due evaluation.",
    "backtest_report_duration_seconds": "Histogram of report generation durations.",
    "backtest_total_runtime_seconds": "Total backtest runtime in seconds.",
    "backtest_peak_memory_mb": "Peak RSS memory in MB.",
    "backtest_processed_per_second": "Throughput in bars per second.",
}


class MetricsCollector:
    """Catalog-driven metrics collector for the backtest pipeline."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for name, metric_type in _METRIC_NAMES_BACKTEST.items():
            self.register(name, metric_type, _METRIC_DESCRIPTIONS.get(name, ""))

    def register(
        self,
        name: str,
        metric_type: MetricType,
        description: str = "",
        buckets: tuple[float, ...] | None = None,
    ) -> None:
        """Register a metric. Re-registering with the same name resets values."""
        if metric_type == MetricType.COUNTER:
            self._counters[name] = Counter(name=name, metric_type=metric_type, description=description)
        elif metric_type == MetricType.GAUGE:
            self._gauges[name] = Gauge(name=name, metric_type=metric_type, description=description)
        elif metric_type == MetricType.HISTOGRAM:
            kwargs: dict[str, Any] = {"name": name, "metric_type": metric_type, "description": description}
            if buckets is not None:
                kwargs["buckets"] = buckets
            self._histograms[name] = Histogram(**kwargs)

    def counter(self, name: str, labels: MetricLabels, value: float = 1.0) -> None:
        if name not in self._counters:
            self._counters[name] = Counter(
                name=name, metric_type=MetricType.COUNTER, description=""
            )
        self._counters[name].inc(labels, value)

    def gauge(self, name: str, labels: MetricLabels, value: float) -> None:
        if name not in self._gauges:
            self._gauges[name] = Gauge(
                name=name, metric_type=MetricType.GAUGE, description=""
            )
        self._gauges[name].set(labels, value)

    def histogram(self, name: str, labels: MetricLabels, value: float) -> None:
        if name not in self._histograms:
            self._histograms[name] = Histogram(
                name=name, metric_type=MetricType.HISTOGRAM, description=""
            )
        self._histograms[name].observe(labels, value)

    def counter_value(self, name: str, labels: MetricLabels) -> float:
        counter = self._counters.get(name)
        if counter is None:
            return 0.0
        return counter.value(labels)

    def gauge_value(self, name: str, labels: MetricLabels) -> float | None:
        gauge = self._gauges.get(name)
        if gauge is None:
            return None
        return gauge.samples.get(labels.key())

    def histogram_snapshot(self, name: str, labels: MetricLabels) -> dict[str, Any] | None:
        histogram = self._histograms.get(name)
        if histogram is None:
            return None
        return histogram.samples.get(labels.key())

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        """Return a JSON-friendly snapshot of all metrics."""
        result: dict[str, list[dict[str, Any]]] = {"counters": [], "gauges": [], "histograms": []}
        for name, metric in self._counters.items():
            for label_key, value in metric.samples.items():
                result["counters"].append(
                    {"name": name, "labels": dict(label_key), "value": value}
                )
        for name, metric in self._gauges.items():
            for label_key, value in metric.samples.items():
                result["gauges"].append(
                    {"name": name, "labels": dict(label_key), "value": value}
                )
        for name, metric in self._histograms.items():
            for label_key, value in metric.samples.items():
                result["histograms"].append(
                    {"name": name, "labels": dict(label_key), **value}
                )
        return result

    def reset(self) -> None:
        for metric in self._counters.values():
            metric.reset()
        for metric in self._gauges.values():
            metric.reset()
        for metric in self._histograms.values():
            metric.reset()


class MetricsRegistry:
    """Process-wide registry of named :class:`MetricsCollector` instances."""

    _DEFAULT_NAME: str = "default"

    def __init__(self) -> None:
        self._collectors: dict[str, MetricsCollector] = {}

    def get(self, name: str = "default") -> MetricsCollector:
        if name not in self._collectors:
            self._collectors[name] = MetricsCollector()
        return self._collectors[name]

    def reset(self, name: str | None = None) -> None:
        if name is None:
            self._collectors.clear()
            return
        if name in self._collectors:
            self._collectors[name].reset()

    def all_snapshots(self) -> dict[str, dict[str, list[dict[str, Any]]]]:
        return {name: collector.snapshot() for name, collector in self._collectors.items()}


_GLOBAL_REGISTRY = MetricsRegistry()


def get_metrics(name: str = "default") -> MetricsCollector:
    """Return the metrics collector registered under ``name``."""
    return _GLOBAL_REGISTRY.get(name)


def reset_metrics(name: str | None = None) -> None:
    """Reset metrics for testing. If ``name`` is None all collectors are cleared."""
    if name is None:
        _GLOBAL_REGISTRY._collectors.clear()
        return
    if name in _GLOBAL_REGISTRY._collectors:
        _GLOBAL_REGISTRY._collectors[name].reset()