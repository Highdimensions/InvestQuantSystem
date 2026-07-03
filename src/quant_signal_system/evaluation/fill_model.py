"""Fill model interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.contracts.signals import ExecutionStatus, SignalEvent


@dataclass(frozen=True, slots=True)
class FillResult:
    executable_price: Decimal | None
    executable_price_source: str | None
    execution_status: ExecutionStatus
    unexecutable_reason: str | None
    signal_delay_seconds: int


@dataclass(frozen=True, slots=True)
class NextBarOpenFillModel:
    fill_model_version: str = "next-bar-open-fill-v1"
    delay_model_version: str = "one-second-delay-v1"

    def fill(self, signal: SignalEvent, path: list[MarketBar]) -> FillResult:
        for bar in path:
            if bar.market_data_time >= signal.executable_time:
                if bar.trading_status in {TradingStatus.HALTED, TradingStatus.CLOSED}:
                    return FillResult(
                        None,
                        None,
                        ExecutionStatus.UNEXECUTABLE,
                        f"bar status {bar.trading_status}",
                        int((bar.market_data_time - signal.event_time).total_seconds()),
                    )
                return FillResult(
                    bar.open_price,
                    "NEXT_BAR_OPEN",
                    ExecutionStatus.EXECUTABLE,
                    None,
                    int((bar.market_data_time - signal.event_time).total_seconds()),
                )
        return FillResult(None, None, ExecutionStatus.UNEXECUTABLE, "NO_EXECUTABLE_BAR", 0)

