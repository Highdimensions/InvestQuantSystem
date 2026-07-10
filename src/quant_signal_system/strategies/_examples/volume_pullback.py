"""Strategy: 缩量回调 (volume-pullback).

A sell-side (risk-reducing) idea for short-horizon mean reversion on A-share
markets. Trigger a SELL action when:

- Price has pulled back by at least ``pullback_threshold`` over the recent
  ``lookback_bars`` bars (price dropped)
- Volume in the latest bar is below the average volume of the prior
  ``lookback_bars`` bars (``volume_ratio < 1``)
- The market regime allows (regime is provided and not RISK_AVOID)

The strategy emits CLEAR_LONG (reduce / close existing long exposure). It does
NOT increase long position.

This module is *not* registered in ``DEFAULT_REGISTRY`` automatically.
Register explicitly via:

    from quant_signal_system.strategies import DEFAULT_REGISTRY
    from quant_signal_system.strategies._examples.volume_pullback import VolumePullbackStrategy

    DEFAULT_REGISTRY.register(VolumePullbackStrategy, params={...})
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.contracts.signals import (
    Direction,
    ExposureEffect,
    SignalAction,
    SignalCandidate,
)
from quant_signal_system.strategies._examples.momentum_v1 import MomentumV1Strategy
from quant_signal_system.strategies.schema import (
    ParamField,
    ParamSchema,
    compute_parameter_hash,
)


@dataclass(frozen=True, slots=True)
class VolumePullbackStrategy:
    """Reduce long exposure on shallow pullback with declining volume."""

    strategy_name: str = "volume-pullback-v1"
    strategy_version: str = "volume-pullback-v1"
    code_version: str = "research-code-v1"
    parameter_hash: str = "volume-pullback-defaults-v1"
    lookback_bars: int = 5
    pullback_threshold: float = 0.01
    volume_ratio_threshold: float = 1.0
    horizon_seconds: int = 900

    @classmethod
    def param_schema(cls) -> ParamSchema:
        return ParamSchema.of(
            ParamField("lookback_bars", int, 5, "bars in the pullback window"),
            ParamField(
                "pullback_threshold", float, 0.01, "minimum negative return over the window"
            ),
            ParamField(
                "volume_ratio_threshold",
                float,
                1.0,
                "max volume_ratio (latest / average of lookback) to confirm thin volume",
            ),
            ParamField("horizon_seconds", int, 900, "default evaluation horizon"),
        )

    def declare_parameters(self) -> tuple[tuple[str, object], ...]:
        return (
            ("lookback_bars", self.lookback_bars),
            ("pullback_threshold", self.pullback_threshold),
            ("volume_ratio_threshold", self.volume_ratio_threshold),
            ("horizon_seconds", self.horizon_seconds),
        )

    @classmethod
    def from_params(
        cls,
        params: Mapping[str, object],
        *,
        strategy_version: str = "volume-pullback-v1",
        code_version: str = "research-code-v1",
    ) -> "VolumePullbackStrategy":
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

        # Use pre-computed pullback features if present, otherwise be silent.
        pullback = float(snapshot.features.get("return_window") or 0.0)
        volume_ratio = float(snapshot.features.get("volume_ratio") or 1.0)

        if pullback > -self.pullback_threshold:
            return None
        if volume_ratio > self.volume_ratio_threshold:
            return None

        return SignalCandidate(
            symbol=bar.symbol,
            direction=Direction.SELL,
            signal_action=SignalAction.REDUCE_LONG,
            exposure_effect=ExposureEffect.DECREASE_LONG,
            market_data_time=bar.market_data_time,
            reference_price=bar.close_price,
            score=Decimal("0.55"),
            confidence=Decimal("0.45"),
            horizon_seconds=self.horizon_seconds,
            reason_codes=("VOLUME_PULLBACK",),
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


__all__ = ["VolumePullbackStrategy", "MomentumV1Strategy"]  # re-export for tests