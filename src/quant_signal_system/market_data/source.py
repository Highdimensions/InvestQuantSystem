"""Provider-facing market data source protocols."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Protocol, Sequence

from quant_signal_system.contracts.market import MarketBar, MarketTick


class MarketDataSource(Protocol):
    """Read or stream already-normalized market data.

    Concrete AKShare, Tushare, RQData, JQData, or broker-terminal adapters must
    map vendor fields before returning these internal contracts.
    """

    def read(
        self,
        *,
        symbols: Sequence[str],
        from_time: datetime,
        to_time: datetime,
    ) -> Iterable[MarketTick | MarketBar]:
        ...

