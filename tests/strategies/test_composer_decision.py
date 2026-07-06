"""Tests for ComposerDecision persistence and conflict attribution.

Uses the same FixedCandidateStrategy test stub from test_composer_conflict.py
to ensure deterministic candidate emission independent of RuleStrategyRuntime's
feature-driven logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.strategies import (
    ComposerDecision,
    ComposerDecisionConflictError,
    ComposerDecisionRepository,
    ConflictPolicy,
    StrategyComposer,
)
from quant_signal_system.contracts.signals import (
    Direction,
    ExposureEffect,
    SignalAction,
    SignalCandidate,
)
from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketBar, TradingStatus


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


MARKET_DATA_TIME = utc("2025-06-02T09:31:00+00:00")


def _bar() -> MarketBar:
    end = MARKET_DATA_TIME
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="300346",
        timeframe="1m",
        bar_start_time=end.replace(minute=end.minute - 1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=42.0,
        high_price=42.0,
        low_price=42.0,
        close_price=42.0,
        volume=1000,
        amount=None,
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        data_source_version="dv1",
        as_of_version="asof-v1",
        source="test",
    )


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap-1",
        symbol="300346",
        market_data_time=MARKET_DATA_TIME,
        generated_at=MARKET_DATA_TIME,
        feature_version="f1",
        lookback_window="3bars",
        features={"close": 42.0, "return_1": -0.02, "volume_ratio": 0.5, "ma_distance": -0.01},
        missing_data_flags=(),
        input_bar_range="2025-06-02T09:29:00..2025-06-02T09:31:00",
    )


@dataclass(frozen=True, slots=True)
class FixedCandidateStrategy:
    """Test stub that always emits the configured candidate (or None)."""
    name: str
    strategy_version: str = "v1"
    code_version: str = "cv1"
    parameter_hash: str = "h"
    horizon_seconds: int = 900
    candidate: SignalCandidate | None = None

    @property
    def version(self) -> str:
        return self.strategy_version

    def declare_parameters(self) -> tuple[tuple[str, object], ...]:
        return ()

    def on_bar(
        self,
        bar: MarketBar,
        snapshot: FeatureSnapshot,
        regime: MarketRegime | None = None,
    ) -> SignalCandidate | None:
        if self.candidate is None:
            return None
        if self.candidate.market_data_time != bar.market_data_time:
            return None
        return self.candidate


def _candidate(
    strategy_name: str,
    direction: Direction,
    score: str = "0.70",
    confidence: str = "0.60",
) -> SignalCandidate:
    return SignalCandidate(
        symbol="300346",
        direction=direction,
        signal_action=(
            SignalAction.BUY if direction == Direction.BUY else SignalAction.RISK_AVOID
        ),
        exposure_effect=(
            ExposureEffect.INCREASE_LONG if direction == Direction.BUY else ExposureEffect.DECREASE_LONG
        ),
        market_data_time=MARKET_DATA_TIME,
        reference_price=Decimal("42.00"),
        score=Decimal(score),
        confidence=Decimal(confidence),
        horizon_seconds=900,
        reason_codes=(f"{strategy_name.upper()}_REASON",),
        invalid_condition=None,
        feature_snapshot=_snapshot(),
        market_regime=None,
        strategy_name=strategy_name,
        strategy_version="v1",
        feature_version="f1",
        code_version="cv1",
        parameter_hash="h",
        data_source_version="dv1",
        as_of_version="asof-v1",
    )


class TestComposerDecisionIdempotency:
    def test_append_once(self) -> None:
        repo = ComposerDecisionRepository()
        runtime = FixedCandidateStrategy("test", candidate=_candidate("test", Direction.BUY))
        composer = StrategyComposer.single(runtime)
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        stored = repo.append(decision)
        assert stored.decision_id == decision.decision_id
        assert repo.get(decision.decision_id) is stored

    def test_append_same_twice_returns_existing(self) -> None:
        repo = ComposerDecisionRepository()
        runtime = FixedCandidateStrategy("test", candidate=_candidate("test", Direction.BUY))
        composer = StrategyComposer.single(runtime)
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        s1 = repo.append(decision)
        s2 = repo.append(decision)
        assert s1 is s2

    def test_append_same_id_different_content_raises(self) -> None:
        repo = ComposerDecisionRepository()
        from quant_signal_system.strategies.composer_decision import _composer_decision_id
        d1 = ComposerDecision(
            decision_id=_composer_decision_id("b1", MARKET_DATA_TIME, "300346", ConflictPolicy.PRIORITY_MAX_CONFIDENCE),
            binding_id="b1",
            market_data_time=MARKET_DATA_TIME,
            symbol="300346",
            policy=ConflictPolicy.PRIORITY_MAX_CONFIDENCE,
            abstained=True,
            abstention_reason="R1",
        )
        d2 = ComposerDecision(
            decision_id=d1.decision_id,
            binding_id="b1",
            market_data_time=MARKET_DATA_TIME,
            symbol="300346",
            policy=ConflictPolicy.PRIORITY_MAX_CONFIDENCE,
            abstained=False,
            abstention_reason=None,
        )
        with pytest.raises(ComposerDecisionConflictError, match="conflict"):
            repo.append(d1)
            repo.append(d2)

    def test_list_for_binding(self) -> None:
        repo = ComposerDecisionRepository()
        for binding_id in ("b1", "b2"):
            runtime = FixedCandidateStrategy("test", candidate=_candidate("test", Direction.BUY))
            composer = StrategyComposer.single(runtime)
            _, decision = composer.decide(_bar(), _snapshot(), None, binding_id=binding_id)
            repo.append(decision)
        b1_decisions = repo.list_for_binding("b1")
        assert len(b1_decisions) == 1
        assert b1_decisions[0].binding_id == "b1"

    def test_list_for_symbol(self) -> None:
        repo = ComposerDecisionRepository()
        runtime = FixedCandidateStrategy("test", candidate=_candidate("test", Direction.BUY))
        composer = StrategyComposer.single(runtime)
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        repo.append(decision)
        symbol_decisions = repo.list_for_symbol("300346")
        assert len(symbol_decisions) == 1
        assert symbol_decisions[0].symbol == "300346"


class TestComposerDecisionAttribution:
    def test_direction_conflict_attributed(self) -> None:
        buy_rt = FixedCandidateStrategy("buy", candidate=_candidate("buy", Direction.BUY))
        sell_rt = FixedCandidateStrategy("sell", candidate=_candidate("sell", Direction.SELL))
        composer = StrategyComposer(runtimes=(buy_rt, sell_rt))
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        assert decision.abstained is True
        assert decision.abstention_reason == "ABSTAIN_DIRECTION_CONFLICT"
        assert len(decision.rejected_candidates) == 2
        assert all("DIRECTION_CONFLICT" in r for r in decision.rejection_reasons)

    def test_unanimous_failure_attributed(self) -> None:
        buy_rt = FixedCandidateStrategy("buy", candidate=_candidate("buy", Direction.BUY))
        sell_rt = FixedCandidateStrategy("sell", candidate=_candidate("sell", Direction.SELL))
        composer = StrategyComposer(
            runtimes=(buy_rt, sell_rt), policy=ConflictPolicy.UNANIMOUS
        )
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        assert decision.abstained is True
        assert decision.abstention_reason == "ABSTAIN_UNANIMOUS_FAILED"
        assert len(decision.rejected_candidates) == 2

    def test_score_weighted_zero_attributed(self) -> None:
        buy_rt = FixedCandidateStrategy("buy", candidate=_candidate("buy", Direction.BUY, score="0.50"))
        sell_rt = FixedCandidateStrategy("sell", candidate=_candidate("sell", Direction.SELL, score="0.50"))
        # Use SCORE_WEIGHTED with zero total score (both BUY but score cancels out)
        # Actually SCORE_WEIGHTED sums signed scores.  Both BUY means positive sum.
        # For zero we need mixed directions with equal magnitude.
        composer = StrategyComposer(
            runtimes=(buy_rt, sell_rt),
            weights=(Decimal("0.5"), Decimal("0.5")),
            policy=ConflictPolicy.SCORE_WEIGHTED,
        )
        # buy*0.5 + sell*(-0.5) = 0.35 - 0.35 = 0
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        assert decision.abstained is True
        assert decision.abstention_reason == "ABSTAIN_WEIGHTED_ZERO"

    def test_single_runtime_no_rejection(self) -> None:
        runtime = FixedCandidateStrategy("test", candidate=_candidate("test", Direction.BUY))
        composer = StrategyComposer.single(runtime)
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        assert decision.abstained is False
        assert len(decision.rejected_candidates) == 0
        assert len(decision.winning_candidates) == 1

    def test_rejection_reason_filled(self) -> None:
        buy_rt = FixedCandidateStrategy("buy", candidate=_candidate("buy", Direction.BUY))
        sell_rt = FixedCandidateStrategy("sell", candidate=_candidate("sell", Direction.SELL))
        composer = StrategyComposer(runtimes=(buy_rt, sell_rt))
        _, decision = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        assert all(r.startswith("DIRECTION_CONFLICT:") for r in decision.rejection_reasons)

    def test_decide_and_on_bar_produce_same_candidate(self) -> None:
        """P1: `decide()` must produce the same candidate as `on_bar()`."""
        runtime = FixedCandidateStrategy("test", candidate=_candidate("test", Direction.BUY))
        composer = StrategyComposer.single(runtime)
        cand_on_bar = composer.on_bar(_bar(), _snapshot())
        cand_decide, _ = composer.decide(_bar(), _snapshot(), None, binding_id="b1")
        assert cand_on_bar == cand_decide
