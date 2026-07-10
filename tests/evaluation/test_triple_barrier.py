"""Tests for triple-barrier configuration and conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.evaluation import BarrierConflictPolicy
from quant_signal_system.evaluation.triple_barrier import (
    TRIPLE_BARRIER_AMBIGUOUS,
    TRIPLE_BARRIER_PROFIT_TAKE,
    TRIPLE_BARRIER_STOP_LOSS,
    TRIPLE_BARRIER_TIME_ONLY,
    TripleBarrierConfig,
    detect_first_barrier_hit,
)


@dataclass(frozen=True)
class _Bar:
    """Minimal stand-in for MarketBar for barrier detection."""
    market_data_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal


def _bar(
    minute: int,
    o: str,
    h: str,
    l: str,
    c: str,
    base: datetime,
) -> _Bar:
    return _Bar(
        market_data_time=base + timedelta(minutes=minute),
        open_price=Decimal(o),
        high_price=Decimal(h),
        low_price=Decimal(l),
        close_price=Decimal(c),
    )


@pytest.fixture
def base_time() -> datetime:
    return datetime(2025, 6, 1, 9, 30, tzinfo=timezone.utc)


class TestTripleBarrierConfig:
    def test_default_validation(self) -> None:
        cfg = TripleBarrierConfig()
        cfg.validate()  # should not raise

    def test_profit_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            TripleBarrierConfig(profit_barrier_ratio=Decimal("-0.01")).validate()

    def test_loss_must_be_negative(self) -> None:
        with pytest.raises(ValueError):
            TripleBarrierConfig(loss_barrier_ratio=Decimal("0.01")).validate()

    def test_time_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            TripleBarrierConfig(time_barrier_seconds=0).validate()

    def test_has_price_barriers(self) -> None:
        cfg_tp = TripleBarrierConfig(profit_barrier_ratio=Decimal("0.02"))
        cfg_sl = TripleBarrierConfig(loss_barrier_ratio=Decimal("-0.01"))
        cfg_none = TripleBarrierConfig()
        assert cfg_tp.has_price_barriers
        assert cfg_sl.has_price_barriers
        assert not cfg_none.has_price_barriers


class TestDetectFirstBarrierHit:
    def test_profit_take_for_long(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            profit_barrier_ratio=Decimal("0.02"),  # +2 %
            loss_barrier_ratio=Decimal("-0.05"),  # -5 %, only TP triggers
        )
        # Executable at 100, TP at 102, bar 1 hits 105 (no SL since low=99 > 95).
        bars = [
            _bar(0, "100", "100.5", "99.5", "100", base_time),
            _bar(1, "100", "105", "99", "104", base_time),
        ]
        label, elapsed = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_PROFIT_TAKE
        assert elapsed == 60

    def test_stop_loss_for_long(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            profit_barrier_ratio=Decimal("0.02"),
            loss_barrier_ratio=Decimal("-0.01"),  # -1 %
        )
        # SL at 99, bar 0 hits low 98.
        bars = [
            _bar(0, "100", "100.5", "98", "99", base_time),
        ]
        label, elapsed = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_STOP_LOSS
        assert elapsed == 0

    def test_profit_take_for_short(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            profit_barrier_ratio=Decimal("0.02"),
            loss_barrier_ratio=Decimal("-0.01"),
        )
        # SELL: TP when price drops 2% (to 98), SL when price rises 1% (to 101)
        bars = [
            _bar(0, "100", "100", "98", "99", base_time),  # TP hit
        ]
        label, elapsed = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=-1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_PROFIT_TAKE

    def test_ambiguous_default_policy(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            profit_barrier_ratio=Decimal("0.02"),
            loss_barrier_ratio=Decimal("-0.01"),
            conflict_policy=BarrierConflictPolicy.AMBIGUOUS,
        )
        # Bar 0: high=105 (TP), low=95 (SL) - both hit
        bars = [_bar(0, "100", "105", "95", "100", base_time)]
        label, _ = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_AMBIGUOUS

    def test_conservative_policy_picks_sl(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            profit_barrier_ratio=Decimal("0.02"),
            loss_barrier_ratio=Decimal("-0.01"),
            conflict_policy=BarrierConflictPolicy.CONSERVATIVE,
        )
        bars = [_bar(0, "100", "105", "95", "100", base_time)]
        label, _ = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_STOP_LOSS

    def test_time_only_when_no_barrier(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            profit_barrier_ratio=Decimal("0.05"),
            loss_barrier_ratio=Decimal("-0.05"),
        )
        # Bar 0: stays within +/- 1 %, neither barrier hit
        bars = [
            _bar(0, "100", "100.5", "99.5", "100", base_time),
            _bar(1, "100", "101", "99", "100", base_time),
        ]
        label, _ = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_TIME_ONLY

    def test_empty_path(self) -> None:
        cfg = TripleBarrierConfig(profit_barrier_ratio=Decimal("0.02"))
        label, elapsed = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=[],
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_TIME_ONLY
        assert elapsed is None

    def test_time_barrier_trigger(self, base_time: datetime) -> None:
        cfg = TripleBarrierConfig(
            time_barrier_seconds=60,
            profit_barrier_ratio=Decimal("0.05"),
            loss_barrier_ratio=Decimal("-0.05"),
        )
        # Bar 0: within bounds. Bar 1 at 120s exceeds time barrier (60s).
        bars = [
            _bar(0, "100", "100.5", "99.5", "100", base_time),
            _bar(2, "100", "101", "99", "100", base_time),
        ]
        label, elapsed = detect_first_barrier_hit(
            executable_price=Decimal("100"),
            direction=1,
            path_bars=bars,
            config=cfg,
        )
        assert label == TRIPLE_BARRIER_TIME_ONLY
        assert elapsed == 120