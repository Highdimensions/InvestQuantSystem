"""Tests for the observability module."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from quant_signal_system.observability.context import (
    LogContext,
    LogContextStore,
    bind_context,
    clear_context,
    current_context,
    get_context_store,
)
from quant_signal_system.observability.structured_logger import (
    LEVEL_DEBUG,
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_WARN,
    JsonFileLogger,
    StructuredLogger,
    get_logger,
    set_default_sink,
    reset_default_sink,
    _StdStreamSink,
)
from quant_signal_system.observability.event_chain import (
    EventChainExporter,
    EventChainEntry,
    EVENT_TYPE_MARKET_BAR_CLOSED,
    EVENT_TYPE_SIGNAL_EVENT,
)
from quant_signal_system.observability.metrics_collector import (
    Counter,
    Gauge,
    Histogram,
    MetricLabels,
    MetricType,
    MetricsCollector,
    get_metrics,
    reset_metrics,
)
from quant_signal_system.observability.alerting import (
    AlertEvent,
    AlertEvaluator,
    AlertRule,
    AlertSeverity,
    TBD,
)


# ---------------------------------------------------------------------------
# Context tests
# ---------------------------------------------------------------------------

class TestLogContext:
    def test_required_run_id(self) -> None:
        ctx = LogContext(run_id="run_001")
        assert ctx.run_id == "run_001"

    def test_optional_fields_default_to_none(self) -> None:
        ctx = LogContext(run_id="run_001")
        assert ctx.binding_id is None
        assert ctx.symbol is None
        assert ctx.event_sequence is None

    def test_with_updates(self) -> None:
        ctx = LogContext(run_id="run_001")
        updated = ctx.with_updates(symbol="300346", event_sequence=5)
        assert updated.run_id == "run_001"
        assert updated.symbol == "300346"
        assert updated.event_sequence == 5
        # Original unchanged
        assert ctx.symbol is None
        assert ctx.event_sequence is None

    def test_to_dict_omits_none(self) -> None:
        ctx = LogContext(run_id="run_001", symbol="300346")
        d = ctx.to_dict()
        assert "run_id" in d
        assert "symbol" in d
        assert "binding_id" not in d  # None value

    def test_to_dict_serializes_datetime(self) -> None:
        ts = datetime(2025, 6, 1, 9, 30, tzinfo=timezone.utc)
        ctx = LogContext(run_id="run_001", market_data_time=ts)
        d = ctx.to_dict()
        assert d["market_data_time"] == "2025-06-01T09:30:00+00:00"


class TestLogContextStore:
    def test_set_and_get(self) -> None:
        store = LogContextStore()
        ctx = LogContext(run_id="run_001")
        token = store.set(ctx)
        assert store.get() is ctx
        store.reset(token)
        assert store.get() is None

    def test_global_store(self) -> None:
        clear_context()
        assert current_context() is None
        bind_context(run_id="run_001")
        assert current_context() is not None
        assert current_context().run_id == "run_001"
        clear_context()
        assert current_context() is None

    def test_bind_context_preserves_existing_fields(self) -> None:
        clear_context()
        bind_context(run_id="run_001", symbol="300346")
        bind_context(event_sequence=5)
        ctx = current_context()
        assert ctx is not None
        assert ctx.run_id == "run_001"
        assert ctx.symbol == "300346"
        assert ctx.event_sequence == 5
        clear_context()


# ---------------------------------------------------------------------------
# Logger tests
# ---------------------------------------------------------------------------

class TestStructuredLogger:
    def test_debug_below_threshold(self) -> None:
        logger = get_logger("test", sink=_StdStreamSink())
        logger.min_level = LEVEL_INFO
        # Should not raise
        logger.debug("should not emit")

    def test_info_above_threshold(self) -> None:
        logger = get_logger("test", sink=_StdStreamSink())
        logger.min_level = LEVEL_DEBUG
        # Should not raise
        logger.info("should emit")


class TestJsonFileLogger:
    def test_emit_single_record(self) -> None:
        logger = JsonFileLogger(name="test", sink=_StdStreamSink())
        bind_context(run_id="run_001", symbol="300346")
        logger.info("bar_processed", total_bars=1)
        records = logger.records
        assert len(records) == 1
        assert records[0]["message"] == "bar_processed"
        assert records[0]["level"] == "INFO"
        assert records[0]["run_id"] == "run_001"
        assert records[0]["symbol"] == "300346"
        assert records[0]["total_bars"] == 1
        clear_context()

    def test_multiple_records(self) -> None:
        logger = JsonFileLogger(name="test", sink=_StdStreamSink())
        bind_context(run_id="run_001")
        logger.info("first")
        logger.warn("second")
        logger.error("third")
        records = logger.records
        assert len(records) == 3
        assert records[0]["level"] == "INFO"
        assert records[1]["level"] == "WARN"
        assert records[2]["level"] == "ERROR"
        clear_context()

    def test_clear(self) -> None:
        logger = JsonFileLogger(name="test", sink=_StdStreamSink())
        bind_context(run_id="run_001")
        logger.info("one")
        logger.clear()
        assert logger.records == []
        clear_context()

    def test_context_auto_merged(self) -> None:
        logger = JsonFileLogger(name="test", sink=_StdStreamSink())
        bind_context(run_id="run_001", binding_id="b001")
        logger.info("signal_created", signal_id="sig_001")
        records = logger.records
        assert records[0]["run_id"] == "run_001"
        assert records[0]["binding_id"] == "b001"
        assert records[0]["signal_id"] == "sig_001"
        clear_context()


# ---------------------------------------------------------------------------
# Event chain tests
# ---------------------------------------------------------------------------

class TestEventChainEntry:
    def test_valid_event_type(self) -> None:
        entry = EventChainEntry(
            run_id="run_001",
            event_type=EVENT_TYPE_MARKET_BAR_CLOSED,
        )
        assert entry.event_type == EVENT_TYPE_MARKET_BAR_CLOSED
        assert entry.event_sequence == 0

    def test_invalid_event_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown event_type"):
            EventChainEntry(run_id="run_001", event_type="InvalidType")

    def test_to_dict(self) -> None:
        ts = datetime(2025, 6, 1, 9, 30, tzinfo=timezone.utc)
        entry = EventChainEntry(
            run_id="run_001",
            binding_id="b001",
            symbol="300346",
            event_type=EVENT_TYPE_SIGNAL_EVENT,
            market_data_time=ts,
            payload={"signal_id": "sig_001"},
        )
        d = entry.to_dict()
        assert d["run_id"] == "run_001"
        assert d["symbol"] == "300346"
        assert d["payload"]["signal_id"] == "sig_001"


class TestEventChainExporter:
    def test_disabled_exporter_is_noop(self) -> None:
        exporter = EventChainExporter(enabled=False)
        entry = exporter.emit(
            EVENT_TYPE_MARKET_BAR_CLOSED, run_id="run_001", symbol="300346"
        )
        assert exporter.entries() == []
        # Entry is still returned
        assert entry is not None

    def test_enabled_exporter_buffers(self) -> None:
        exporter = EventChainExporter(enabled=True)
        bind_context(run_id="run_001")
        exporter.emit(EVENT_TYPE_MARKET_BAR_CLOSED, run_id="run_001", symbol="300346")
        assert len(exporter.entries()) == 1
        clear_context()

    def test_sequence_increments(self) -> None:
        exporter = EventChainExporter(enabled=True)
        bind_context(run_id="run_001")
        e1 = exporter.emit(EVENT_TYPE_MARKET_BAR_CLOSED, run_id="run_001")
        e2 = exporter.emit(EVENT_TYPE_SIGNAL_EVENT, run_id="run_001")
        assert e2.event_sequence > e1.event_sequence
        clear_context()

    def test_flush_to_path(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        exporter = EventChainExporter(output_path=path, enabled=True)
        bind_context(run_id="run_001")
        exporter.emit(EVENT_TYPE_MARKET_BAR_CLOSED, run_id="run_001", symbol="300346")
        exporter.emit(EVENT_TYPE_SIGNAL_EVENT, run_id="run_001", symbol="300346")
        exporter.flush()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        clear_context()


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

class TestMetricLabels:
    def test_default_empty(self) -> None:
        labels = MetricLabels()
        assert labels.to_dict() == {}

    def test_partial_labels(self) -> None:
        labels = MetricLabels(run_id="run_001", symbol="300346")
        d = labels.to_dict()
        assert d["run_id"] == "run_001"
        assert d["symbol"] == "300346"
        assert "binding_id" not in d

    def test_key_stability(self) -> None:
        l1 = MetricLabels(run_id="run_001", symbol="300346")
        l2 = MetricLabels(run_id="run_001", symbol="300346")
        assert l1.key() == l2.key()

    def test_key_order_insensitive(self) -> None:
        l1 = MetricLabels(run_id="run_001", symbol="300346")
        l2 = MetricLabels(symbol="300346", run_id="run_001")
        assert l1.key() == l2.key()


class TestCounter:
    def test_increment(self) -> None:
        c = Counter(name="test_counter", metric_type=MetricType.COUNTER)
        labels = MetricLabels(run_id="run_001")
        c.inc(labels, 1.0)
        c.inc(labels, 2.0)
        assert c.value(labels) == 3.0

    def test_negative_increment_raises(self) -> None:
        c = Counter(name="test_counter", metric_type=MetricType.COUNTER)
        labels = MetricLabels()
        with pytest.raises(ValueError):
            c.inc(labels, -1.0)

    def test_different_labels_independent(self) -> None:
        c = Counter(name="test_counter", metric_type=MetricType.COUNTER)
        l1 = MetricLabels(run_id="run_001")
        l2 = MetricLabels(run_id="run_002")
        c.inc(l1, 5.0)
        c.inc(l2, 3.0)
        assert c.value(l1) == 5.0
        assert c.value(l2) == 3.0


class TestGauge:
    def test_set(self) -> None:
        g = Gauge(name="test_gauge", metric_type=MetricType.GAUGE)
        labels = MetricLabels(run_id="run_001")
        g.set(labels, 42.0)
        assert g.value(labels) == 42.0
        g.set(labels, 100.0)
        assert g.value(labels) == 100.0

    def test_inc_dec(self) -> None:
        g = Gauge(name="test_gauge", metric_type=MetricType.GAUGE)
        labels = MetricLabels()
        g.set(labels, 10.0)
        g.inc(labels, 5.0)
        assert g.value(labels) == 15.0
        g.dec(labels, 3.0)
        assert g.value(labels) == 12.0


class TestHistogram:
    def test_observe(self) -> None:
        h = Histogram(name="test_hist", metric_type=MetricType.HISTOGRAM)
        labels = MetricLabels()
        h.observe(labels, 0.5)
        h.observe(labels, 1.0)
        snap = h.samples.get(labels.key())
        assert snap is not None
        assert snap["count"] == 2
        assert snap["sum"] == 1.5


class TestMetricsCollector:
    def test_counter(self) -> None:
        mc = MetricsCollector()
        labels = MetricLabels(run_id="run_001", symbol="300346")
        mc.counter("backtest_bars_processed_total", labels, 1.0)
        mc.counter("backtest_bars_processed_total", labels, 1.0)
        assert mc.counter_value("backtest_bars_processed_total", labels) == 2.0

    def test_gauge(self) -> None:
        mc = MetricsCollector()
        labels = MetricLabels(run_id="run_001")
        mc.gauge("backtest_evaluation_backlog", labels, 10.0)
        assert mc.gauge_value("backtest_evaluation_backlog", labels) == 10.0

    def test_snapshot(self) -> None:
        mc = MetricsCollector()
        mc.counter("backtest_bars_processed_total", MetricLabels(run_id="run_001"), 5.0)
        mc.gauge("backtest_evaluation_backlog", MetricLabels(run_id="run_001"), 3.0)
        snap = mc.snapshot()
        assert "counters" in snap
        assert "gauges" in snap
        assert any(c["name"] == "backtest_bars_processed_total" for c in snap["counters"])

    def test_reset(self) -> None:
        mc = MetricsCollector()
        mc.counter("backtest_bars_processed_total", MetricLabels(run_id="run_001"), 5.0)
        mc.reset()
        assert mc.counter_value("backtest_bars_processed_total", MetricLabels(run_id="run_001")) == 0.0


class TestGlobalMetrics:
    def test_get_and_reset(self) -> None:
        # Use a unique label to avoid pollution from prior tests
        labels = MetricLabels(run_id="unique_test_get_reset")
        mc = get_metrics()
        mc.counter("backtest_bars_processed_total", labels, 5.0)
        # Reset all metrics
        reset_metrics()
        # After reset, calling get_metrics() returns a fresh collector
        mc_after = get_metrics()
        assert mc_after.counter_value("backtest_bars_processed_total", labels) == 0.0


# ---------------------------------------------------------------------------
# Alerting tests
# ---------------------------------------------------------------------------

class TestAlertRule:
    def test_is_tbd_with_nan(self) -> None:
        rule = AlertRule(name="test", metric="test", threshold=TBD)
        assert rule.is_tbd()

    def test_is_tbd_with_value(self) -> None:
        rule = AlertRule(name="test", metric="test", threshold=5.0)
        assert not rule.is_tbd()


class TestAlertEvaluator:
    def test_tbd_rule_not_fired(self) -> None:
        mc = MetricsCollector()
        mc.counter("backtest_missing_bars_total", MetricLabels(run_id="run_001"), 100.0)
        evaluator = AlertEvaluator(metrics=mc)
        alerts = evaluator.evaluate("run_001")
        # No TBD rule should fire
        assert len(alerts) == 0

    def test_rule_fires_on_condition(self) -> None:
        mc = MetricsCollector()
        labels = MetricLabels(run_id="unique_signal_persist_test")
        mc.counter("backtest_signal_persist_failure_total", labels, 3.0)
        evaluator = AlertEvaluator(metrics=mc)
        alerts = evaluator.evaluate("run_001")
        assert any(a.alert_name == "signal_persist_failure_p1" for a in alerts)

    def test_all_rules_have_runbook(self) -> None:
        for rule in AlertEvaluator.DEFAULT_RULES:
            assert rule.runbook, f"Rule {rule.name} has no runbook"

    def test_fired_alerts_accumulated(self) -> None:
        mc = MetricsCollector()
        labels = MetricLabels(run_id="unique_fired_alerts_test")
        mc.counter("backtest_signal_persist_failure_total", labels, 1.0)
        evaluator = AlertEvaluator(metrics=mc)
        evaluator.evaluate("run_001")
        assert len(evaluator.fired_alerts) >= 1
