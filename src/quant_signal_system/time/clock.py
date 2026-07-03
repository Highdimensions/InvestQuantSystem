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

