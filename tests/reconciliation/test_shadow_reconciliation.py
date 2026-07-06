"""Light shadow reconciliation tests, mirroring
``tests/consistency/test_live_vs_replay.py`` but pinned under the
``tests/reconciliation`` package described in the Phase 7 plan.
"""

from __future__ import annotations

from datetime import timedelta
from random import Random

from quant_signal_system.contracts.signals import Direction
from quant_signal_system.reporting.reconciliation import ShadowRunComparator
from tests.consistency.test_live_vs_replay import _event, _replay_signal_ids
from tests.helpers.orchestration import make_bar, utc


def _bars() -> list:
    """Volume-spike bars that reliably fire ``RuleStrategyRuntime``."""
    start = utc(2025, 6, 2, 9, 30)
    rng = Random(7)
    return [
        make_bar(
            "300346",
            start + timedelta(minutes=i),
            close=42.0 + rng.uniform(-2, 2),
            volume=2000 + rng.choice([0, 4000, 8000]),
        )
        for i in range(30)
    ]


def _ids() -> tuple[str, ...]:
    return _replay_signal_ids(_bars())


class TestShadowReconciliation:
    def test_perfect_match(self) -> None:
        ids = _ids()
        replay = [_event(sid, Direction.BUY) for sid in ids]
        shadow = [_event(sid, Direction.BUY) for sid in ids]
        report = ShadowRunComparator().compare(replay_signals=replay, shadow_signals=shadow)
        assert report.unexplained_differences == 0

    def test_one_missing(self) -> None:
        ids = _ids()
        replay = [_event(sid, Direction.BUY) for sid in ids]
        shadow = [_event(sid, Direction.BUY) for sid in ids[:-1]]
        report = ShadowRunComparator().compare(replay_signals=replay, shadow_signals=shadow)
        assert len(report.missing_in_shadow) == 1

    def test_one_extra(self) -> None:
        ids = _ids()
        replay = [_event(sid, Direction.BUY) for sid in ids]
        shadow = replay + [_event("phantom", Direction.BUY)]
        report = ShadowRunComparator().compare(replay_signals=replay, shadow_signals=shadow)
        assert len(report.extra_in_shadow) == 1

    def test_one_direction_mismatch(self) -> None:
        ids = _ids()
        replay = [_event(sid, Direction.BUY) for sid in ids]
        shadow = [
            _event(sid, Direction.SELL if i == 0 else Direction.BUY) for i, sid in enumerate(ids)
        ]
        report = ShadowRunComparator().compare(replay_signals=replay, shadow_signals=shadow)
        assert len(report.direction_mismatches) == 1
