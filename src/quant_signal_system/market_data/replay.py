"""Historical replay source over standardized, versioned MarketBar data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from quant_signal_system.contracts.market import MarketBar, MarketDataValidationError
from quant_signal_system.market_data.repository import InMemoryMarketDataRepository


@dataclass(frozen=True, slots=True)
class MarketDataReplaySource:
    repository: InMemoryMarketDataRepository

    def read(
        self,
        *,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
        timeframe: str,
        data_source_version: str,
        as_of_version: str,
    ) -> Iterator[MarketBar]:
        previous_time: datetime | None = None
        for bar in self.repository.read_bars(
            symbol=symbol,
            from_time=from_time,
            to_time=to_time,
            timeframe=timeframe,
            data_source_version=data_source_version,
            as_of_version=as_of_version,
        ):
            bar.validate(require_closed=True)
            if previous_time is not None and bar.market_data_time <= previous_time:
                raise MarketDataValidationError("replay source emitted non-increasing bars")
            previous_time = bar.market_data_time
            yield bar

