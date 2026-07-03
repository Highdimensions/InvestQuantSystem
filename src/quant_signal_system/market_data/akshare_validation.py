"""Single-source AKShare validation helpers.

This intentionally validates AKShare by itself. It does not compare against
Tushare or any other provider, because dual-source reconciliation is explicitly
out of scope for this implementation pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.market_data.akshare_source import AKShareMarketDataSource
from quant_signal_system.market_data.quarantine import QuarantineRecord


@dataclass(frozen=True, slots=True)
class AKShareValidationResult:
    requested_symbols: tuple[str, ...]
    bars_count: int
    quarantine_count: int
    missing_symbols: tuple[str, ...]
    data_source_version: str
    as_of_version: str

    @property
    def passed(self) -> bool:
        return self.bars_count > 0 and not self.missing_symbols


@dataclass(frozen=True, slots=True)
class AKShareValidator:
    source: AKShareMarketDataSource

    def validate_window(
        self,
        *,
        symbols: list[str],
        from_time: datetime,
        to_time: datetime,
    ) -> AKShareValidationResult:
        bars: list[MarketBar] = []
        quarantine: list[QuarantineRecord] = []
        for item in self.source.read_with_quarantine(
            symbols=symbols,
            from_time=from_time,
            to_time=to_time,
        ):
            if isinstance(item, MarketBar):
                bars.append(item)
            else:
                quarantine.append(item)

        symbols_with_bars = {bar.symbol for bar in bars}
        normalized_requested = {self.source._akshare_symbol(symbol) for symbol in symbols}
        missing = tuple(sorted(normalized_requested - symbols_with_bars))
        return AKShareValidationResult(
            requested_symbols=tuple(symbols),
            bars_count=len(bars),
            quarantine_count=len(quarantine),
            missing_symbols=missing,
            data_source_version=self.source.profile.data_source_version,
            as_of_version=self.source.profile.as_of_version,
        )

