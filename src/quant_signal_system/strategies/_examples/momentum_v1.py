"""Example strategy: simple momentum confirmation.

This module is **not** registered with `DEFAULT_REGISTRY` automatically. It
exists as a reference implementation that downstream tests and sample
onboarding scripts can use without polluting the production registry.

To use it in production, import and register explicitly:

    from quant_signal_system.strategies import DEFAULT_REGISTRY
    from quant_signal_system.strategies._examples.momentum_v1 import MomentumV1Strategy

    DEFAULT_REGISTRY.register(MomentumV1Strategy, yaml_path=...)

or pass inline overrides:

    DEFAULT_REGISTRY.register(
        MomentumV1Strategy,
        params={"lookback_bars": 5, "return_threshold": 0.005},
    )
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
from quant_signal_system.strategies.schema import (
    ParamField,
    ParamSchema,
    compute_parameter_hash,
)


@dataclass(frozen=True, slots=True)
class MomentumV1Strategy:
    strategy_name: str = "momentum-v1"
    strategy_version: str = "momentum-v1"
    code_version: str = "research-code-v1"
    parameter_hash: str = "momentum-defaults-v1"
    horizon_seconds: int = 900
    return_threshold: float = 0.005

    @classmethod
    def param_schema(cls) -> ParamSchema:
        return ParamSchema.of(
            ParamField("return_threshold", float, 0.005, "minimum return_1 to trigger"),
            ParamField("horizon_seconds", int, 900, "default evaluation horizon"),
        )

    def declare_parameters(self) -> tuple[tuple[str, object], ...]:
        return (
            ("return_threshold", self.return_threshold),
            ("horizon_seconds", self.horizon_seconds),
        )

    @classmethod
    def from_params(
        cls,
        params: Mapping[str, object],
        *,
        strategy_version: str = "momentum-v1",
        code_version: str = "research-code-v1",
    ) -> "MomentumV1Strategy":
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
        return_1 = float(snapshot.features.get("return_1") or 0.0)
        if return_1 < self.return_threshold:
            return None

        return SignalCandidate(
            symbol=bar.symbol,
            direction=Direction.BUY,
            signal_action=SignalAction.BUY,
            exposure_effect=ExposureEffect.INCREASE_LONG,
            market_data_time=bar.market_data_time,
            reference_price=bar.close_price,
            score=Decimal("0.55"),
            confidence=Decimal("0.50"),
            horizon_seconds=self.horizon_seconds,
            reason_codes=("MOMENTUM_CONFIRMED",),
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