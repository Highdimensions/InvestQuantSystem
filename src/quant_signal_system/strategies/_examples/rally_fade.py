"""Strategy: 冲高回落 (rally-fade).

Detect an intraday rally that fails to hold by the close. The setup:

- The high of the current bar is significantly above the recent reference price
  (``rally_threshold`` over the lookback mean).
- The close of the current bar is back inside the prior range
  (``close_within_range = True`` indicates the bar rallied but reverted).

This pattern is often traded as a SELL/REDUCE_LONG signal: the buyers failed
to defend the breakout. The strategy does NOT increase long position.

This module is *not* registered in ``DEFAULT_REGISTRY`` automatically.
Register explicitly via:

    from quant_signal_system.strategies import DEFAULT_REGISTRY
    from quant_signal_system.strategies._examples.rally_fade import RallyFadeStrategy

    DEFAULT_REGISTRY.register(RallyFadeStrategy, params={...})
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
class RallyFadeStrategy:
    """Reduce long exposure when an intraday rally fails to hold."""

    strategy_name: str = "rally-fade-v1"
    strategy_version: str = "rally-fade-v1"
    code_version: str = "research-code-v1"
    parameter_hash: str = "rally-fade-defaults-v1"
    lookback_bars: int = 5
    rally_threshold: float = 0.02
    horizon_seconds: int = 900

    @classmethod
    def param_schema(cls) -> ParamSchema:
        return ParamSchema.of(
            ParamField("lookback_bars", int, 5, "bars in the reference window"),
            ParamField(
                "rally_threshold",
                float,
                0.02,
                "minimum absolute return of bar.high over the lookback mean",
            ),
            ParamField("horizon_seconds", int, 900, "default evaluation horizon"),
        )

    def declare_parameters(self) -> tuple[tuple[str, object], ...]:
        return (
            ("lookback_bars", self.lookback_bars),
            ("rally_threshold", self.rally_threshold),
            ("horizon_seconds", self.horizon_seconds),
        )

    @classmethod
    def from_params(
        cls,
        params: Mapping[str, object],
        *,
        strategy_version: str = "rally-fade-v1",
        code_version: str = "research-code-v1",
    ) -> "RallyFadeStrategy":
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

        # rally_amplitude and rally_fade features are expected to be pre-computed.
        amplitude = float(snapshot.features.get("rally_amplitude") or 0.0)
        fade_flag = bool(snapshot.features.get("rally_fade") or False)
        if not fade_flag:
            return None
        if amplitude < self.rally_threshold:
            return None

        return SignalCandidate(
            symbol=bar.symbol,
            direction=Direction.SELL,
            signal_action=SignalAction.REDUCE_LONG,
            exposure_effect=ExposureEffect.DECREASE_LONG,
            market_data_time=bar.market_data_time,
            reference_price=bar.close_price,
            score=Decimal("0.50"),
            confidence=Decimal("0.40"),
            horizon_seconds=self.horizon_seconds,
            reason_codes=("RALLY_FADE",),
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


__all__ = ["RallyFadeStrategy", "MomentumV1Strategy"]  # re-export for tests