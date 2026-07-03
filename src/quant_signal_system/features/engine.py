"""Small closed-bar feature engine for v1 rule strategies."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from quant_signal_system.contracts.features import FeatureSnapshot
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.time.clock import Clock, SystemClock


@dataclass(slots=True)
class RollingFeatureEngine:
    feature_version: str = "rolling-feature-v1"
    lookback: int = 3
    clock: Clock = field(default_factory=SystemClock)
    _bars_by_symbol: dict[str, list[MarketBar]] = field(default_factory=dict)

    def update_closed_bar(self, bar: MarketBar) -> FeatureSnapshot:
        bar.validate(require_closed=True)
        bars = self._bars_by_symbol.setdefault(bar.symbol, [])
        bars.append(bar)
        bars.sort(key=lambda item: item.market_data_time)
        window = bars[-self.lookback :]

        missing_flags: list[str] = []
        if len(window) < self.lookback:
            missing_flags.append("INSUFFICIENT_LOOKBACK")

        close = bar.close_price
        previous_close = window[-2].close_price if len(window) >= 2 else close
        returns_1 = float((close - previous_close) / previous_close) if previous_close else 0.0
        avg_volume = self._avg([item.volume for item in window if item.volume is not None])
        volume_ratio = (
            float(bar.volume / avg_volume) if bar.volume is not None and avg_volume not in (None, 0) else None
        )
        ma_close = self._avg([item.close_price for item in window])
        ma_distance = float((close - ma_close) / ma_close) if ma_close else 0.0

        input_range = f"{window[0].market_data_time.isoformat()}..{window[-1].market_data_time.isoformat()}"
        snapshot_id = hashlib.sha256(
            f"{bar.symbol}|{bar.market_data_time.isoformat()}|{self.feature_version}|{input_range}".encode(
                "utf-8"
            )
        ).hexdigest()[:16]
        return FeatureSnapshot(
            schema_version="feature-snapshot-v1",
            feature_snapshot_id=snapshot_id,
            symbol=bar.symbol,
            market_data_time=bar.market_data_time,
            generated_at=self.clock.now(),
            feature_version=self.feature_version,
            lookback_window=f"{len(window)}bars",
            features={
                "return_1": returns_1,
                "volume_ratio": volume_ratio,
                "ma_distance": ma_distance,
                "close": float(close),
            },
            missing_data_flags=tuple(missing_flags),
            input_bar_range=input_range,
        )

    def _avg(self, values: list[Decimal]) -> Decimal | None:
        if not values:
            return None
        return sum(values, Decimal("0")) / Decimal(len(values))
