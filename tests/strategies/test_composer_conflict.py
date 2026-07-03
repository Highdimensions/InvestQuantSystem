"""Tests for the multi-strategy composer and conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.contracts.signals import (
    Direction,
    ExposureEffect,
    SignalAction,
    SignalCandidate,
)
from quant_signal_system.strategies import (
    ComposerConflictError,
    ConflictPolicy,
    RuleStrategyRuntime,
    StrategyComposer,
)
from quant_signal_system.strategies.composer import (
    describe_composer,
    replace_candidate,
)


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _bar(close: str = "10.10") -> MarketBar:
    end = utc("2024-07-03T01:33:00+00:00")
    price = Decimal(close)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=end.replace(minute=end.minute - 1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=price,
        high_price=price + Decimal("0.10"),
        low_price=price - Decimal("0.10"),
        close_price=price,
        volume=Decimal("100"),
        amount=price * Decimal("100"),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source="AKShare",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version="feature-snapshot-v1",
        feature_snapshot_id="snap-1",
        symbol="000001",
        market_data_time=utc("2024-07-03T01:33:00+00:00"),
        generated_at=utc("2024-07-03T01:33:00+00:00"),
        feature_version="rolling-feature-v1",
        lookback_window="3bars",
        features={"close": 10.10, "return_1": 0.01, "volume_ratio": 2.0, "ma_distance": 0.01},
        missing_data_flags=(),
        input_bar_range="2024-07-03T01:31:00..2024-07-03T01:33:00",
    )


@dataclass(frozen=True, slots=True)
class FixedCandidateStrategy:
    """Test stub that always emits the configured candidate (or None)."""

    name: str
    strategy_version: str
    code_version: str
    parameter_hash: str
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


def _candidate(strategy: FixedCandidateStrategy, direction: Direction, score: str, conf: str) -> SignalCandidate:
    return SignalCandidate(
        symbol="000001",
        direction=direction,
        signal_action=(
            SignalAction.BUY if direction == Direction.BUY else SignalAction.RISK_AVOID
        ),
        exposure_effect=(
            ExposureEffect.INCREASE_LONG if direction == Direction.BUY else ExposureEffect.DECREASE_LONG
        ),
        market_data_time=utc("2024-07-03T01:33:00+00:00"),
        reference_price=Decimal("10.10"),
        score=Decimal(score),
        confidence=Decimal(conf),
        horizon_seconds=strategy.horizon_seconds,
        reason_codes=(f"{strategy.name.upper()}_REASON",),
        invalid_condition=None,
        feature_snapshot=_snapshot(),
        market_regime=None,
        strategy_name=strategy.name,
        strategy_version=strategy.strategy_version,
        feature_version="rolling-feature-v1",
        code_version=strategy.code_version,
        parameter_hash=strategy.parameter_hash,
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def test_composer_requires_at_least_one_runtime() -> None:
    with pytest.raises(ComposerConflictError, match="at least one"):
        StrategyComposer(runtimes=())


def test_composer_single_passes_through() -> None:
    runtime = RuleStrategyRuntime()
    composer = StrategyComposer.single(runtime)
    result = composer.on_bar(_bar(), _snapshot())
    assert result is None or result.strategy_name == "baseline-rules"


def test_composer_priority_max_confidence_picks_higher_priority_on_agreement() -> None:
    bar = _bar()
    snap = _snapshot()
    primary = FixedCandidateStrategy(
        name="primary",
        strategy_version="primary-v1",
        code_version="research-code-v1",
        parameter_hash="primary-hash",
        candidate=_candidate(
            FixedCandidateStrategy(
                "primary", "primary-v1", "research-code-v1", "primary-hash"
            ),
            Direction.BUY,
            "0.70",
            "0.55",
        ),
    )
    secondary = FixedCandidateStrategy(
        name="secondary",
        strategy_version="secondary-v1",
        code_version="research-code-v1",
        parameter_hash="secondary-hash",
        candidate=_candidate(
            FixedCandidateStrategy(
                "secondary", "secondary-v1", "research-code-v1", "secondary-hash"
            ),
            Direction.BUY,
            "0.65",
            "0.80",
        ),
    )
    composer = StrategyComposer(runtimes=(primary, secondary))
    result = composer.on_bar(bar, snap)
    assert result is not None
    assert result.strategy_name == "primary"
    assert "AGGREGATED:secondary" in result.reason_codes


def test_composer_priority_max_confidence_abstains_on_direction_conflict() -> None:
    bar = _bar()
    snap = _snapshot()
    buy_strategy = FixedCandidateStrategy(
        name="buy_one",
        strategy_version="v1",
        code_version="research-code-v1",
        parameter_hash="buy-hash",
        candidate=_candidate(
            FixedCandidateStrategy("buy_one", "v1", "research-code-v1", "buy-hash"),
            Direction.BUY,
            "0.70",
            "0.55",
        ),
    )
    sell_strategy = FixedCandidateStrategy(
        name="sell_one",
        strategy_version="v1",
        code_version="research-code-v1",
        parameter_hash="sell-hash",
        candidate=_candidate(
            FixedCandidateStrategy("sell_one", "v1", "research-code-v1", "sell-hash"),
            Direction.SELL,
            "0.60",
            "0.55",
        ),
    )
    composer = StrategyComposer(runtimes=(buy_strategy, sell_strategy))
    result = composer.on_bar(bar, snap)
    assert result is None


def test_composer_unanimous_passes_when_all_agree() -> None:
    bar = _bar()
    snap = _snapshot()
    candidates_args = [
        (
            "one",
            "v1",
            "research-code-v1",
            "hash-one",
            "0.50",
            "0.50",
        ),
        (
            "two",
            "v1",
            "research-code-v1",
            "hash-two",
            "0.65",
            "0.55",
        ),
    ]
    runtimes: list[FixedCandidateStrategy] = []
    for name, version, code, hash_, score, conf in candidates_args:
        runtimes.append(
            FixedCandidateStrategy(
                name=name,
                strategy_version=version,
                code_version=code,
                parameter_hash=hash_,
                candidate=_candidate(
                    FixedCandidateStrategy(name, version, code, hash_),
                    Direction.BUY,
                    score,
                    conf,
                ),
            )
        )
    composer = StrategyComposer(runtimes=tuple(runtimes), policy=ConflictPolicy.UNANIMOUS)
    result = composer.on_bar(bar, snap)
    assert result is not None
    assert result.direction == Direction.BUY
    assert all(code.startswith("UNANIMOUS:") for code in result.reason_codes if code.startswith("UNANIMOUS:"))


def test_composer_unanimous_abstains_on_conflict() -> None:
    bar = _bar()
    snap = _snapshot()
    buy_strategy = FixedCandidateStrategy(
        name="buy_one",
        strategy_version="v1",
        code_version="research-code-v1",
        parameter_hash="buy-hash",
        candidate=_candidate(
            FixedCandidateStrategy("buy_one", "v1", "research-code-v1", "buy-hash"),
            Direction.BUY,
            "0.50",
            "0.50",
        ),
    )
    sell_strategy = FixedCandidateStrategy(
        name="sell_one",
        strategy_version="v1",
        code_version="research-code-v1",
        parameter_hash="sell-hash",
        candidate=_candidate(
            FixedCandidateStrategy("sell_one", "v1", "research-code-v1", "sell-hash"),
            Direction.SELL,
            "0.50",
            "0.50",
        ),
    )
    composer = StrategyComposer(
        runtimes=(buy_strategy, sell_strategy),
        policy=ConflictPolicy.UNANIMOUS,
    )
    assert composer.on_bar(bar, snap) is None


def test_composer_score_weighted_picks_buy_when_score_positive() -> None:
    bar = _bar()
    snap = _snapshot()
    candidates = []
    for name, score, conf in [("one", "0.80", "0.60"), ("two", "0.30", "0.55")]:
        candidates.append(
            FixedCandidateStrategy(
                name=name,
                strategy_version="v1",
                code_version="research-code-v1",
                parameter_hash=f"hash-{name}",
                candidate=_candidate(
                    FixedCandidateStrategy(name, "v1", "research-code-v1", f"hash-{name}"),
                    Direction.BUY,
                    score,
                    conf,
                ),
            )
        )
    composer = StrategyComposer(
        runtimes=tuple(candidates),
        weights=(Decimal("1.0"), Decimal("1.0")),
        policy=ConflictPolicy.SCORE_WEIGHTED,
    )
    result = composer.on_bar(bar, snap)
    assert result is not None
    assert result.direction == Direction.BUY
    assert any(code.startswith("WEIGHTED_SCORE:") for code in result.reason_codes)


def test_composer_score_weighted_picks_sell_when_score_negative() -> None:
    bar = _bar()
    snap = _snapshot()
    candidates = []
    for name, direction, score in [
        ("one", Direction.SELL, "0.80"),
        ("two", Direction.BUY, "0.20"),
    ]:
        candidates.append(
            FixedCandidateStrategy(
                name=name,
                strategy_version="v1",
                code_version="research-code-v1",
                parameter_hash=f"hash-{name}",
                candidate=_candidate(
                    FixedCandidateStrategy(name, "v1", "research-code-v1", f"hash-{name}"),
                    direction,
                    score,
                    "0.60",
                ),
            )
        )
    composer = StrategyComposer(
        runtimes=tuple(candidates),
        weights=(Decimal("1.0"), Decimal("1.0")),
        policy=ConflictPolicy.SCORE_WEIGHTED,
    )
    result = composer.on_bar(bar, snap)
    assert result is not None
    assert result.direction == Direction.SELL


def test_composer_score_weighted_abstains_on_zero() -> None:
    bar = _bar()
    snap = _snapshot()
    candidates = []
    for name in ["one", "two"]:
        candidates.append(
            FixedCandidateStrategy(
                name=name,
                strategy_version="v1",
                code_version="research-code-v1",
                parameter_hash=f"hash-{name}",
                candidate=SignalCandidate(
                    symbol="000001",
                    direction=Direction.HOLD,
                    signal_action=SignalAction.HOLD,
                    exposure_effect=ExposureEffect.NO_ACTION,
                    market_data_time=utc("2024-07-03T01:33:00+00:00"),
                    reference_price=Decimal("10.10"),
                    score=Decimal("0.50"),
                    confidence=Decimal("0.60"),
                    horizon_seconds=900,
                    reason_codes=(f"{name}_REASON",),
                    invalid_condition=None,
                    feature_snapshot=_snapshot(),
                    market_regime=None,
                    strategy_name=name,
                    strategy_version="v1",
                    feature_version="rolling-feature-v1",
                    code_version="research-code-v1",
                    parameter_hash=f"hash-{name}",
                    data_source_version="akshare-exploration-v1",
                    as_of_version="asof-research-v1",
                ),
            )
        )
    composer = StrategyComposer(
        runtimes=tuple(candidates),
        weights=(Decimal("1.0"), Decimal("1.0")),
        policy=ConflictPolicy.SCORE_WEIGHTED,
    )
    assert composer.on_bar(bar, snap) is None


def test_composer_score_weighted_requires_positive_weights() -> None:
    candidates = []
    for name in ["one", "two"]:
        candidates.append(
            FixedCandidateStrategy(
                name=name,
                strategy_version="v1",
                code_version="research-code-v1",
                parameter_hash=f"hash-{name}",
                candidate=_candidate(
                    FixedCandidateStrategy(name, "v1", "research-code-v1", f"hash-{name}"),
                    Direction.BUY,
                    "0.50",
                    "0.60",
                ),
            )
        )
    with pytest.raises(ComposerConflictError, match="positive"):
        StrategyComposer(
            runtimes=tuple(candidates),
            weights=(Decimal("1.0"), Decimal("0")),
            policy=ConflictPolicy.SCORE_WEIGHTED,
        )


def test_composer_no_candidates_returns_none() -> None:
    bar = _bar()
    snap = _snapshot()
    silent = FixedCandidateStrategy(
        name="silent",
        strategy_version="v1",
        code_version="research-code-v1",
        parameter_hash="silent-hash",
    )
    composer = StrategyComposer(runtimes=(silent,))
    assert composer.on_bar(bar, snap) is None


def test_composer_priority_max_confidence_picks_higher_confidence_on_ties() -> None:
    bar = _bar()
    snap = _snapshot()
    candidates = []
    for name, score, conf in [
        ("first", "0.50", "0.55"),
        ("second", "0.50", "0.80"),
    ]:
        candidates.append(
            FixedCandidateStrategy(
                name=name,
                strategy_version="v1",
                code_version="research-code-v1",
                parameter_hash=f"hash-{name}",
                candidate=_candidate(
                    FixedCandidateStrategy(name, "v1", "research-code-v1", f"hash-{name}"),
                    Direction.BUY,
                    score,
                    conf,
                ),
            )
        )
    composer = StrategyComposer(runtimes=tuple(candidates))
    result = composer.on_bar(bar, snap)
    assert result is not None
    assert result.strategy_name == "first"


def test_replace_candidate_returns_copy_with_overrides() -> None:
    candidate = _candidate(
        FixedCandidateStrategy("base", "v1", "research-code-v1", "hash-base"),
        Direction.BUY,
        "0.5",
        "0.5",
    )
    new = replace_candidate(candidate, reason_codes=("NEW",), direction=Direction.SELL)
    assert new is not candidate
    assert new.reason_codes == ("NEW",)
    assert new.direction == Direction.SELL


def test_replace_candidate_returns_original_when_no_overrides() -> None:
    candidate = _candidate(
        FixedCandidateStrategy("base", "v1", "research-code-v1", "hash-base"),
        Direction.BUY,
        "0.5",
        "0.5",
    )
    assert replace_candidate(candidate) is candidate


def test_describe_composer_lists_runtimes() -> None:
    composer = StrategyComposer.single(RuleStrategyRuntime())
    description = describe_composer(composer)
    assert description.startswith("PRIORITY_MAX_CONFIDENCE[")
    assert "baseline-rules" in description