"""Structured logger interface and JSON file sink.

Implements the logging field schema defined in
``docs/architecture/backtest-observability.md`` Section 2.1. The default
backend is a deterministic JSON-line writer suitable for offline tests and
batch backtests. Callers can replace the sink for production deployments
without touching the rest of the codebase.
"""

from __future__ import annotations

import io
import json
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ClassVar

from quant_signal_system.observability.context import current_context


LogLevel = str
LEVEL_DEBUG: LogLevel = "DEBUG"
LEVEL_INFO: LogLevel = "INFO"
LEVEL_WARN: LogLevel = "WARN"
LEVEL_ERROR: LogLevel = "ERROR"


@dataclass(frozen=True, slots=True)
class LogRecord:
    """A single structured log entry."""

    timestamp: datetime
    level: LogLevel
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    logger_name: str = ""
    fields: dict[str, Any] = field(default_factory=dict)


class LogSink(ABC):
    """Abstract destination for :class:`LogRecord` entries."""

    @abstractmethod
    def write(self, record: LogRecord) -> None:
        """Write one record to the sink."""

    def close(self) -> None:
        """Release any held resources. Default no-op."""


class _StdStreamSink(LogSink):
    """Write JSON lines to a stream (defaults to stderr)."""

    def __init__(self, stream: Any | None = None) -> None:
        self._stream = stream or sys.stderr

    def write(self, record: LogRecord) -> None:
        payload = {
            "timestamp": record.timestamp.isoformat(),
            "level": record.level,
            "message": record.message,
            "logger": record.logger_name,
        }
        merged = dict(payload)
        merged.update(record.context)
        merged.update(record.fields)
        self._stream.write(json.dumps(merged, ensure_ascii=False) + "\n")
        flush = getattr(self._stream, "flush", None)
        if callable(flush):
            flush()


@dataclass
class StructuredLogger:
    """Logger that produces :class:`LogRecord` objects from the active context.

    Each logger has a name (typically the module path) and dispatches records
    to the registered sink. The active :class:`LogContext` is merged into every
    record automatically so the caller only needs to supply the per-call fields.
    """

    _LEVEL_ORDER: ClassVar[dict[LogLevel, int]] = {
        LEVEL_DEBUG: 0,
        LEVEL_INFO: 1,
        LEVEL_WARN: 2,
        LEVEL_ERROR: 3,
    }

    name: str
    sink: LogSink
    min_level: LogLevel = LEVEL_INFO

    def _should_emit(self, level: LogLevel) -> bool:
        return self._LEVEL_ORDER[level] >= self._LEVEL_ORDER[self.min_level]

    def _emit(self, level: LogLevel, message: str, **fields: Any) -> None:
        if not self._should_emit(level):
            return
        ctx = current_context()
        context_dict = ctx.to_dict() if ctx is not None else {}
        record = LogRecord(
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            context=context_dict,
            logger_name=self.name,
            fields=dict(fields),
        )
        self.sink.write(record)

    def debug(self, message: str, **fields: Any) -> None:
        self._emit(LEVEL_DEBUG, message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit(LEVEL_INFO, message, **fields)

    def warn(self, message: str, **fields: Any) -> None:
        self._emit(LEVEL_WARN, message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit(LEVEL_ERROR, message, **fields)


@dataclass
class JsonFileLogger(StructuredLogger):
    """Logger that appends JSON lines to an in-memory buffer.

    Intended for tests and offline batches. The buffer is exposed via the
    :attr:`records` property so tests can assert on emitted records without
    relying on stderr.
    """

    buffer: io.StringIO = field(default_factory=io.StringIO)

    def __post_init__(self) -> None:
        # Re-build the sink pointing at our buffer.
        self.sink = _StdStreamSink(self.buffer)

    @property
    def records(self) -> list[dict[str, Any]]:
        """Return the parsed log entries captured so far."""
        lines = [line for line in self.buffer.getvalue().splitlines() if line.strip()]
        return [json.loads(line) for line in lines]

    def clear(self) -> None:
        self.buffer = io.StringIO()
        self.sink = _StdStreamSink(self.buffer)


_DEFAULT_SINK: LogSink | None = None


def set_default_sink(sink: LogSink) -> None:
    """Install the sink used by :func:`get_logger`."""
    global _DEFAULT_SINK
    _DEFAULT_SINK = sink


def reset_default_sink() -> None:
    """Restore the default sink to the package default (stderr)."""
    global _DEFAULT_SINK
    _DEFAULT_SINK = None


def get_logger(name: str, *, sink: LogSink | None = None) -> StructuredLogger:
    """Return a :class:`StructuredLogger` bound to the active sink.

    Callers may pass ``sink`` explicitly to capture output for tests; otherwise
    the global default (stderr) is used.
    """
    resolved = sink if sink is not None else (_DEFAULT_SINK or _StdStreamSink())
    return StructuredLogger(name=name, sink=resolved)