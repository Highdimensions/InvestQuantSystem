"""Clock abstractions for deterministic replay and evaluation tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc


class Clock(Protocol):
    def now(self) -> datetime:
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(slots=True)
class FrozenClock:
    current_time: datetime

    def __post_init__(self) -> None:
        require_aware_utc(self.current_time, "current_time")

    def now(self) -> datetime:
        return self.current_time

    def advance(self, delta: timedelta) -> datetime:
        if delta.total_seconds() < 0:
            raise MarketDataValidationError("FrozenClock cannot move backwards")
        self.current_time += delta
        return self.current_time


@dataclass(slots=True)
class VirtualClock:
    """A frozen clock that tracks history and supports jumping to a target time.

    ``VirtualClock`` is the standard clock for backtest runs.  It never consults
    the system clock and produces a deterministic sequence of time values.
    """

    current_time: datetime
    _history: list[datetime] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        require_aware_utc(self.current_time, "current_time")
        object.__setattr__(self, "_history", [])

    def now(self) -> datetime:
        return self.current_time

    def advance(self, delta: timedelta) -> datetime:
        if delta.total_seconds() < 0:
            raise MarketDataValidationError("VirtualClock cannot move backwards")
        self.current_time += delta
        self._history.append(self.current_time)
        return self.current_time

    def advance_to(self, target: datetime) -> datetime:
        """Advance the clock directly to ``target``.

        This is the preferred method for backtest engines that process
        pre-sorted bars: instead of repeated ``advance(delta)`` calls, call
        ``advance_to(bar.market_data_time)`` once per bar.

        Raises ``MarketDataValidationError`` if ``target`` is before
        ``current_time``.
        """
        require_aware_utc(target, "target")
        if target < self.current_time:
            raise MarketDataValidationError(
                f"VirtualClock cannot jump backwards: current={self.current_time.isoformat()} "
                f"target={target.isoformat()}"
            )
        if target > self.current_time:
            object.__setattr__(self, "current_time", target)
            self._history.append(target)
        return self.current_time

    def history(self) -> tuple[datetime, ...]:
        """Return an immutable snapshot of all time values this clock visited."""
        return tuple(self._history)

