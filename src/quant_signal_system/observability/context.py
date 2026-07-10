"""Request-scoped logging context.

Stores the structured logging fields defined in
``docs/architecture/backtest-observability.md`` Section 2.1.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class LogContext:
    """Structured logging context bound to the current execution unit.

    All fields are optional except ``run_id`` which is required to anchor a
    run-scoped audit trail. The remaining fields are populated as information
    becomes available along the signal evaluation pipeline.
    """

    run_id: str
    binding_id: str | None = None
    symbol: str | None = None
    market_data_time: datetime | None = None
    event_sequence: int | None = None
    current_virtual_time: datetime | None = None
    source_data_partition: str | None = None
    strategy_version: str | None = None
    data_version: str | None = None
    warning_code: str | None = None
    error_category: str | None = None
    extra: dict[str, Any] = field(default_factory=dict, kw_only=True)

    def with_updates(self, **changes: Any) -> LogContext:
        """Return a new context with the given fields overridden."""
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict, omitting None values."""
        payload: dict[str, Any] = {}
        for key in (
            "run_id",
            "binding_id",
            "symbol",
            "market_data_time",
            "event_sequence",
            "current_virtual_time",
            "source_data_partition",
            "strategy_version",
            "data_version",
            "warning_code",
            "error_category",
        ):
            value = getattr(self, key)
            if value is not None:
                if isinstance(value, datetime):
                    payload[key] = value.isoformat()
                else:
                    payload[key] = value
        for key, value in self.extra.items():
            payload[key] = value
        return payload


class LogContextStore:
    """Thread/async-safe holder for the active ``LogContext``.

    Backed by :class:`contextvars.ContextVar` so context propagates correctly
    through threaded executors and ``asyncio`` tasks.
    """

    _CONTEXT_VAR: ContextVar[LogContext | None] = ContextVar(
        "quant_signal_system_log_context", default=None
    )

    @classmethod
    def get(cls) -> LogContext | None:
        return cls._CONTEXT_VAR.get()

    @classmethod
    def set(cls, context: LogContext) -> Any:
        """Set the active context. Returns the token used to restore."""
        return cls._CONTEXT_VAR.set(context)

    @classmethod
    def reset(cls, token: Any) -> None:
        cls._CONTEXT_VAR.reset(token)

    @classmethod
    def clear(cls) -> None:
        cls._CONTEXT_VAR.set(None)


_GLOBAL_STORE = LogContextStore()


def get_context_store() -> LogContextStore:
    """Return the global :class:`LogContextStore`."""
    return _GLOBAL_STORE


def current_context() -> LogContext | None:
    """Return the active ``LogContext`` or ``None``."""
    return _GLOBAL_STORE.get()


def bind_context(
    *,
    run_id: str | None = None,
    binding_id: str | None = None,
    symbol: str | None = None,
    market_data_time: datetime | None = None,
    event_sequence: int | None = None,
    current_virtual_time: datetime | None = None,
    source_data_partition: str | None = None,
    strategy_version: str | None = None,
    data_version: str | None = None,
    warning_code: str | None = None,
    error_category: str | None = None,
    **extra: Any,
) -> LogContext:
    """Create or update the active ``LogContext`` for the current execution unit.

    Returns the new context so callers may capture it for explicit passing.
    Only fields that are not ``None`` are merged into the existing context;
    pass ``None`` (or omit the argument) to preserve the existing value.
    """
    existing = _GLOBAL_STORE.get()
    base = existing or LogContext(run_id=run_id or "")
    updates: dict[str, Any] = {}
    if run_id is not None:
        updates["run_id"] = run_id
    if binding_id is not None:
        updates["binding_id"] = binding_id
    if symbol is not None:
        updates["symbol"] = symbol
    if market_data_time is not None:
        updates["market_data_time"] = market_data_time
    if event_sequence is not None:
        updates["event_sequence"] = event_sequence
    if current_virtual_time is not None:
        updates["current_virtual_time"] = current_virtual_time
    if source_data_partition is not None:
        updates["source_data_partition"] = source_data_partition
    if strategy_version is not None:
        updates["strategy_version"] = strategy_version
    if data_version is not None:
        updates["data_version"] = data_version
    if warning_code is not None:
        updates["warning_code"] = warning_code
    if error_category is not None:
        updates["error_category"] = error_category
    if extra:
        merged_extra = dict(base.extra)
        merged_extra.update(extra)
        updates["extra"] = merged_extra
    new_context = base.with_updates(**updates)
    _GLOBAL_STORE.set(new_context)
    return new_context


def clear_context() -> None:
    """Remove the active ``LogContext`` from the global store."""
    _GLOBAL_STORE.clear()