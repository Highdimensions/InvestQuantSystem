"""Explainable baseline rule strategies.

`RuleStrategyRuntime` implements the three rule families that anchored the
early baselines:

* volume breakout (`breakout_volume_ratio`),
* pullback (`pullback_threshold`),
* spike fade (`spike_threshold`).

The class exposes the `StrategyRuntime` Protocol structurally by providing
the required properties, `on_bar`, and `declare_parameters`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.contracts.signals import (
    Direction,
    ExposureEffect,
    SignalAction,
    SignalCandidate,
)
from quant_signal_system.strategies.schema import (
    ParamField,
    ParamSchema,
    compute_parameter_hash,
)


@dataclass(frozen=True, slots=True)
class RuleStrategyRuntime:
    strategy_name: str = "baseline-rules"
    strategy_version: str = "baseline-rules-v1"
    code_version: str = "research-code-v1"
    parameter_hash: str = "baseline-defaults-v1"
    horizon_seconds: int = 900
    breakout_volume_ratio: float = 1.5
    pullback_threshold: float = -0.01
    spike_threshold: float = 0.02

    @classmethod
    def param_schema(cls) -> ParamSchema:
        return ParamSchema.of(
            ParamField("breakout_volume_ratio", float, 1.5, "volume ratio required to flag a breakout"),
            ParamField("pullback_threshold", float, -0.01, "return_1 below this triggers pullback"),
            ParamField("spike_threshold", float, 0.02, "return_1 above this triggers spike fade"),
            ParamField("horizon_seconds", int, 900, "default evaluation horizon"),
        )

    def declare_parameters(self) -> tuple[tuple[str, object], ...]:
        return (
            ("breakout_volume_ratio", self.breakout_volume_ratio),
            ("pullback_threshold", self.pullback_threshold),
            ("spike_threshold", self.spike_threshold),
            ("horizon_seconds", self.horizon_seconds),
        )

    @classmethod
    def from_params(
        cls,
        params: Mapping[str, object],
        *,
        strategy_version: str = "baseline-rules-v1",
        code_version: str = "research-code-v1",
    ) -> "RuleStrategyRuntime":
        resolved = cls.param_schema().validate(params)
        return cls(
            strategy_version=strategy_version,
            code_version=code_version,
            parameter_hash=compute_parameter_hash(resolved),
            **resolved,
        )

    @property
    def name(self) -> str:
        return self.strategy_name

    @property
    def version(self) -> str:
        return self.strategy_version

    def on_bar(
        self,
        bar: MarketBar,
        snapshot: FeatureSnapshot,
        regime: MarketRegime | None = None,
    ) -> SignalCandidate | None:
        bar.validate(require_closed=True)
        if snapshot.missing_data_flags:
            return None
        features = snapshot.features
        return_1 = float(features.get("return_1") or 0.0)
        volume_ratio = features.get("volume_ratio")
        ma_distance = float(features.get("ma_distance") or 0.0)

        if volume_ratio is not None and float(volume_ratio) >= self.breakout_volume_ratio and return_1 > 0:
            return self._candidate(
                bar,
                snapshot,
                regime,
                direction=Direction.BUY,
                action=SignalAction.BUY,
                exposure=ExposureEffect.INCREASE_LONG,
                score=Decimal("0.70"),
                confidence=Decimal("0.60"),
                reason_codes=("VOLUME_BREAKOUT",),
            )
        if return_1 <= self.pullback_threshold and ma_distance < 0:
            return self._candidate(
                bar,
                snapshot,
                regime,
                direction=Direction.SELL,
                action=SignalAction.RISK_AVOID,
                exposure=ExposureEffect.DECREASE_LONG,
                score=Decimal("0.60"),
                confidence=Decimal("0.55"),
                reason_codes=("PULLBACK_RISK",),
            )
        if return_1 >= self.spike_threshold and ma_distance > 0:
            return self._candidate(
                bar,
                snapshot,
                regime,
                direction=Direction.SELL,
                action=SignalAction.REDUCE_LONG,
                exposure=ExposureEffect.DECREASE_LONG,
                score=Decimal("0.65"),
                confidence=Decimal("0.55"),
                reason_codes=("SPIKE_FADE_RISK",),
            )
        return None

    def _candidate(
        self,
        bar: MarketBar,
        snapshot: FeatureSnapshot,
        regime: MarketRegime | None,
        *,
        direction: Direction,
        action: SignalAction,
        exposure: ExposureEffect,
        score: Decimal,
        confidence: Decimal,
        reason_codes: tuple[str, ...],
    ) -> SignalCandidate:
        return SignalCandidate(
            symbol=bar.symbol,
            direction=direction,
            signal_action=action,
            exposure_effect=exposure,
            market_data_time=bar.market_data_time,
            reference_price=bar.close_price,
            score=score,
            confidence=confidence,
            horizon_seconds=self.horizon_seconds,
            reason_codes=reason_codes,
            invalid_condition=None,
            feature_snapshot=snapshot,
            market_regime=regime,
            strategy_name=self.strategy_name,
            strategy_version=self.strategy_version,
            feature_version=snapshot.feature_version,
            code_version=self.code_version,
            parameter_hash=self.parameter_hash,
            data_source_version=bar.data_source_version,
            as_of_version=bar.as_of_version,
        )


def _params_view(runtime: RuleStrategyRuntime) -> Mapping[str, object]:
    return MappingProxyType(dict(runtime.declare_parameters()))