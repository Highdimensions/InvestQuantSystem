"""Simple versioned A-share trading calendar interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from quant_signal_system.contracts.market import require_aware_utc


@dataclass(frozen=True, slots=True)
class SimpleAshareTradingCalendar:
    """A small deterministic calendar for tests and first-stage research.

    It models normal weekday A-share sessions and optional holidays. It is not a
    final exchange calendar source; callers must version it and may replace it
    later without changing strategy code.
    """

    calendar_version: str = "simple-ashare-calendar-v1"
    market_timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Shanghai"))
    holidays: frozenset[date] = frozenset()

    morning_start: time = time(9, 30)
    morning_end: time = time(11, 30)
    afternoon_start: time = time(13, 0)
    afternoon_end: time = time(15, 0)

    def is_trading_day(self, value: date) -> bool:
        return value.weekday() < 5 and value not in self.holidays

    def is_session_time(self, timestamp: datetime, symbol: str | None = None) -> bool:
        require_aware_utc(timestamp, "timestamp")
        local = timestamp.astimezone(self.market_timezone)
        if not self.is_trading_day(local.date()):
            return False
        local_time = local.time()
        return (self.morning_start <= local_time <= self.morning_end) or (
            self.afternoon_start <= local_time <= self.afternoon_end
        )

    def next_session_time(self, timestamp: datetime) -> datetime:
        require_aware_utc(timestamp, "timestamp")
        local = timestamp.astimezone(self.market_timezone)
        candidate_day = local.date()

        while True:
            if not self.is_trading_day(candidate_day):
                candidate_day += timedelta(days=1)
                continue
            morning_start_dt = datetime.combine(
                candidate_day, self.morning_start, tzinfo=self.market_timezone
            )
            afternoon_start_dt = datetime.combine(
                candidate_day, self.afternoon_start, tzinfo=self.market_timezone
            )
            afternoon_end_dt = datetime.combine(
                candidate_day, self.afternoon_end, tzinfo=self.market_timezone
            )

            if local <= morning_start_dt:
                return morning_start_dt.astimezone(timezone.utc)
            if local.time() <= self.morning_end:
                return local.astimezone(timezone.utc)
            if local <= afternoon_start_dt:
                return afternoon_start_dt.astimezone(timezone.utc)
            if local <= afternoon_end_dt:
                return local.astimezone(timezone.utc)
            candidate_day += timedelta(days=1)
            local = datetime.combine(candidate_day, time(0, 0), tzinfo=self.market_timezone)

    def next_evaluation_time(
        self,
        event_time: datetime,
        horizon_seconds: int,
        symbol: str | None = None,
    ) -> datetime:
        require_aware_utc(event_time, "event_time")
        target = event_time + timedelta(seconds=horizon_seconds)
        return self.next_session_time(target)

