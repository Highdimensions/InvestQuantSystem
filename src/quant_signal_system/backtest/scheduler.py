"""Backtest scheduler: stable event ordering and virtual clock management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from quant_signal_system.backtest.run_spec import BacktestRunSpec
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.time.clock import VirtualClock

if TYPE_CHECKING:
    from quant_signal_system.backtest.manifest import RunWarning
    from quant_signal_system.universe.resolver import UniverseResolver


# Event priority constants (ADR-BT-005)
_PRIORITY_MARKET_BAR = 2


@dataclass
class BacktestScheduler:
    """Manages virtual clock progression and stable bar ordering for backtest runs.

    Responsibilities:
    - Virtual clock advancement (advance_to market_data_time)
    - Stable bar sorting (market_data_time + symbol alpha)
    - Out-of-order bar detection and warning generation
    - Universe change detection
    """

    spec: BacktestRunSpec
    clock: VirtualClock
    _last_time: datetime | None = field(default=None)
    _out_of_order_count: int = field(default=0)
    _last_warning_code: str = field(default="")

    def advance_to_bar(self, bar: MarketBar) -> datetime:
        """Advance the virtual clock to the bar's market_data_time.

        Records an out-of-order warning if bar.market_data_time < current_time.
        For out-of-order bars the clock is not moved (backward jumps are prohibited)
        but the bar's market_data_time is still recorded as _last_time so subsequent
        bars are evaluated against the correct high-water mark.
        """
        bar.validate(require_closed=True)
        is_oow = (
            self._last_time is not None
            and bar.market_data_time < self._last_time
        )
        if is_oow:
            self._out_of_order_count += 1
            self._last_warning_code = "OUT_OF_ORDER_BAR"
            self._last_time = bar.market_data_time
            return self.clock.now()
        self.clock.advance_to(bar.market_data_time)
        self._last_time = self.clock.now()
        return self.clock.now()

    def current_time(self) -> datetime:
        """Return the current virtual clock time."""
        return self.clock.now()

    def stable_sort_bars(self, bars: list[MarketBar]) -> list[MarketBar]:
        """Return bars sorted by (market_data_time, symbol) for deterministic ordering.

        Sorting is stable: bars with identical (market_data_time, symbol) preserve
        their relative order from the input list.
        """
        return sorted(bars, key=lambda b: (b.market_data_time, b.symbol))

    def out_of_order_count(self) -> int:
        """Return the number of out-of-order bars detected."""
        return self._out_of_order_count

    def last_warning_code(self) -> str:
        """Return the code of the most recent warning."""
        return self._last_warning_code

    def universe_needs_switch(
        self,
        resolver: UniverseResolver,
        binding_id: str,
        universe_id: str,
        current_version: str,
        current_time: datetime,
    ) -> bool:
        """Return True if the universe for binding_id has changed at current_time."""
        try:
            snapshot = resolver.resolve(universe_id, current_time)
            if snapshot.universe_version != current_version:
                return True
        except Exception:
            return False
        return False

    def build_time_range_warning(
        self,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
    ) -> RunWarning:
        """Build a MISSING_BAR warning for a time range gap."""
        from quant_signal_system.backtest.manifest import RunWarning

        return RunWarning(
            warning_code="MISSING_BAR",
            severity="warn",
            message=f"bar gap detected for {symbol} between {from_time.isoformat()} and {to_time.isoformat()}",
            affected_symbols=(symbol,),
            affected_time_range=(from_time, to_time),
            count=1,
        )
