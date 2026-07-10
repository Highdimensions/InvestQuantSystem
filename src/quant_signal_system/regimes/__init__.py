"""Market regime engine: classify short-horizon regime from features.

Implements the recommendation in
``docs/architecture/testing-and-evaluation.md`` Section 8.6: a deterministic,
feature-driven classifier that tags each symbol at each ``market_data_time``
with one of ``TREND``, ``RANGE``, ``BREAKOUT``, ``HIGH_VOLATILITY``, ``RISK_AVOID``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Mapping


class RegimeLabel(StrEnum):
    TREND = "TREND"
    RANGE = "RANGE"
    BREAKOUT = "BREAKOUT"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    RISK_AVOID = "RISK_AVOID"


@dataclass(frozen=True, slots=True)
class RegimeConfig:
    """Configurable thresholds for the simple rule-based classifier.

    These are deliberately simple defaults; they are calibrated offline against
    benchmark runs and may be tuned once the backtest pipeline stabilises.
    """

    schema_version: str = "regime-config-v1"
    # Volatility bucket: std-dev of 1-bar returns.
    high_vol_threshold: float = 0.01
    # Momentum: |return_window| above this is considered trending.
    trend_threshold: float = 0.015
    # Breakout: requires both trending momentum AND sufficient volume.
    breakout_volume_ratio: float = 1.5
    # RISK_AVOID: confidence below this from the upstream classifier is overridden.
    risk_avoid_confidence_below: float = 0.20

    def regime_config_version(self) -> str:
        payload = (
            f"{self.high_vol_threshold}|{self.trend_threshold}|"
            f"{self.breakout_volume_ratio}|{self.risk_avoid_confidence_below}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class MarketRegimeEngine:
    """Rule-based regime classifier.

    Inputs are a flat feature mapping produced by the rolling feature engine
    plus a derived ``signal_confidence`` for the RISK_AVOID fallback.
    """

    config: RegimeConfig = field(default_factory=RegimeConfig)

    def classify(
        self,
        symbol: str,
        market_data_time: datetime,
        features: Mapping[str, float | int | str | None],
        signal_confidence: float = 1.0,
        data_source_version: str = "",
        as_of_version: str = "",
    ) -> "ClassifiedRegime":
        std_dev = float(features.get("return_stddev") or 0.0)
        return_window = float(features.get("return_window") or 0.0)
        volume_ratio = float(features.get("volume_ratio") or 1.0)

        if signal_confidence < self.config.risk_avoid_confidence_below:
            label = RegimeLabel.RISK_AVOID
        elif std_dev >= self.config.high_vol_threshold:
            label = RegimeLabel.HIGH_VOLATILITY
        elif abs(return_window) >= self.config.trend_threshold:
            if volume_ratio >= self.config.breakout_volume_ratio:
                label = RegimeLabel.BREAKOUT
            else:
                label = RegimeLabel.TREND
        else:
            label = RegimeLabel.RANGE

        return ClassifiedRegime(
            regime_id=_deterministic_regime_id(
                symbol=symbol,
                market_data_time=market_data_time,
                label=label,
                config_version=self.config.regime_config_version(),
                data_source_version=data_source_version,
                as_of_version=as_of_version,
            ),
            symbol=symbol,
            market_data_time=market_data_time,
            label=label,
            confidence=_confidence_from_features(label, features),
            generated_at=market_data_time,
            config_version=self.config.regime_config_version(),
            data_source_version=data_source_version,
            as_of_version=as_of_version,
        )


@dataclass(frozen=True, slots=True)
class ClassifiedRegime:
    """Concrete classification result for one symbol at one bar."""

    schema_version: str = "classified-regime-v1"
    regime_id: str = ""
    symbol: str = ""
    market_data_time: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    label: RegimeLabel = RegimeLabel.RANGE
    confidence: float = 0.0
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    regime_version: str = "regime-v1"
    config_version: str = ""
    data_source_version: str = ""
    as_of_version: str = ""

    def is_risk_avoid(self) -> bool:
        return self.label == RegimeLabel.RISK_AVOID

    def to_dict(self) -> dict[str, object]:
        def _serialize(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj
        return _serialize(
            {
                "schema_version": self.schema_version,
                "regime_id": self.regime_id,
                "symbol": self.symbol,
                "market_data_time": self.market_data_time,
                "label": str(self.label.value),
                "confidence": self.confidence,
                "generated_at": self.generated_at,
                "regime_version": self.regime_version,
                "config_version": self.config_version,
                "data_source_version": self.data_source_version,
                "as_of_version": self.as_of_version,
            }
        )


def _confidence_from_features(
    label: RegimeLabel, features: Mapping[str, float | int | str | None]
) -> float:
    """Compute a simple confidence score from feature magnitudes.

    Returns 0..1. The formula is intentionally trivial so the value is
    auditable; calibration is a future task.
    """
    std_dev = float(features.get("return_stddev") or 0.0)
    if label == RegimeLabel.RISK_AVOID:
        return 1.0
    if label == RegimeLabel.HIGH_VOLATILITY:
        return min(1.0, std_dev / 0.05)
    if label == RegimeLabel.BREAKOUT:
        return min(1.0, std_dev / 0.03 + 0.3)
    if label == RegimeLabel.TREND:
        return 0.5
    return 0.3


def _deterministic_regime_id(
    *,
    symbol: str,
    market_data_time: datetime,
    label: RegimeLabel,
    config_version: str,
    data_source_version: str,
    as_of_version: str,
) -> str:
    payload = "|".join(
        [
            symbol,
            market_data_time.isoformat(),
            str(label.value),
            config_version,
            data_source_version,
            as_of_version,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


__all__ = [
    "ClassifiedRegime",
    "MarketRegimeEngine",
    "RegimeConfig",
    "RegimeLabel",
]  # re-export for tests