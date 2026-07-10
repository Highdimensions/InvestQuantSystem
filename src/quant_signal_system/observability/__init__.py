"""Observability: structured logging, metrics collection, event chain export, alerting.

Provides the production-readiness infrastructure for the quant signal system,
aligned with ``docs/architecture/backtest-observability.md`` and
``docs/architecture/testing-and-evaluation.md`` Section 8.
"""

from __future__ import annotations

from quant_signal_system.observability.context import (
    LogContext,
    LogContextStore,
    bind_context,
    clear_context,
    current_context,
    get_context_store,
)
from quant_signal_system.observability.event_chain import (
    EVENT_TYPE_MARKET_BAR_CLOSED,
    EVENT_TYPE_FEATURE_SNAPSHOT,
    EVENT_TYPE_SIGNAL_CANDIDATE,
    EVENT_TYPE_COMPOSER_DECISION,
    EVENT_TYPE_SIGNAL_EVENT,
    EVENT_TYPE_ORDER_INTENT,
    EVENT_TYPE_PAPER_FILL,
    EVENT_TYPE_EVALUATION_TASK,
    EventChainEntry,
    EventChainExporter,
)
from quant_signal_system.observability.structured_logger import (
    LEVEL_DEBUG,
    LEVEL_INFO,
    LEVEL_WARN,
    LEVEL_ERROR,
    LogLevel,
    StructuredLogger,
    JsonFileLogger,
    get_logger,
    set_default_sink,
    reset_default_sink,
)
from quant_signal_system.observability.metrics_collector import (
    MetricLabels,
    MetricType,
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    MetricsRegistry,
    get_metrics,
    reset_metrics,
)
from quant_signal_system.observability.alerting import (
    AlertSeverity,
    AlertRule,
    AlertEvent,
    AlertEvaluator,
    AlertRouter,
)

__all__ = [
    # context
    "LogContext",
    "LogContextStore",
    "bind_context",
    "clear_context",
    "current_context",
    "get_context_store",
    # logger
    "LogLevel",
    "LEVEL_DEBUG",
    "LEVEL_INFO",
    "LEVEL_WARN",
    "LEVEL_ERROR",
    "StructuredLogger",
    "JsonFileLogger",
    "get_logger",
    "set_default_sink",
    "reset_default_sink",
    # event chain
    "EventChainEntry",
    "EventChainExporter",
    "EVENT_TYPE_MARKET_BAR_CLOSED",
    "EVENT_TYPE_FEATURE_SNAPSHOT",
    "EVENT_TYPE_SIGNAL_CANDIDATE",
    "EVENT_TYPE_COMPOSER_DECISION",
    "EVENT_TYPE_SIGNAL_EVENT",
    "EVENT_TYPE_ORDER_INTENT",
    "EVENT_TYPE_PAPER_FILL",
    "EVENT_TYPE_EVALUATION_TASK",
    # metrics
    "MetricLabels",
    "MetricType",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsCollector",
    "MetricsRegistry",
    "get_metrics",
    "reset_metrics",
    # alerting
    "AlertSeverity",
    "AlertRule",
    "AlertEvent",
    "AlertEvaluator",
    "AlertRouter",
]