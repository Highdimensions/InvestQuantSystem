"""Tests for time/clock.py — VirtualClock."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.time.clock import VirtualClock


class TestVirtualClockAdvance:
    def test_initial_time(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert clock.now() == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_advance_delta_positive(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        t = clock.advance(timedelta(hours=1))
        assert t == datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
        assert clock.now() == datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_advance_delta_zero(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        t = clock.advance(timedelta(0))
        assert t == datetime(2025, 1, 1, tzinfo=timezone.utc)

    def test_advance_negative_raises(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        with pytest.raises(MarketDataValidationError, match="cannot move backwards"):
            clock.advance(timedelta(hours=-1))

    def test_advance_to_forward(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        target = datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
        t = clock.advance_to(target)
        assert t == target
        assert clock.now() == target

    def test_advance_to_same_time_no_change(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        target = datetime(2025, 1, 1, tzinfo=timezone.utc)
        t = clock.advance_to(target)
        assert t == target
        assert clock.now() == target

    def test_advance_to_backwards_raises(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 6, 15, tzinfo=timezone.utc))
        target = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(MarketDataValidationError, match="cannot jump backwards"):
            clock.advance_to(target)

    def test_advance_to_naive_raises(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        with pytest.raises(MarketDataValidationError, match="timezone-aware"):
            clock.advance_to(datetime(2025, 6, 15))  # naive

    def test_history_records_advances(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        clock.advance(timedelta(hours=1))
        clock.advance_to(datetime(2025, 6, 15, tzinfo=timezone.utc))
        history = clock.history()
        assert len(history) == 2
        assert history[0] == datetime(2025, 1, 1, 1, 0, 0, tzinfo=timezone.utc)
        assert history[1] == datetime(2025, 6, 15, tzinfo=timezone.utc)

    def test_history_empty_initially(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert clock.history() == ()

    def test_history_immutable(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        clock.advance(timedelta(hours=1))
        history = clock.history()
        assert isinstance(history, tuple)
        # Confirm it's a snapshot (old view unchanged after new advance)
        clock.advance(timedelta(hours=2))
        assert len(history) == 1
        assert len(clock.history()) == 2

    def test_multiple_advance_to_same_time(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        clock.advance_to(datetime(2025, 6, 15, tzinfo=timezone.utc))
        clock.advance_to(datetime(2025, 6, 15, tzinfo=timezone.utc))
        assert len(clock.history()) == 1  # no duplicate entries for same time

    def test_advance_to_same_time_not_recorded(self) -> None:
        clock = VirtualClock(current_time=datetime(2025, 1, 1, tzinfo=timezone.utc))
        clock.advance_to(datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert clock.history() == ()  # no entry for same time
