"""Market data contracts with time, price, and version semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any


class MarketDataValidationError(ValueError):
    """Raised when market data would violate replay/live correctness rules."""


class TradingStatus(StrEnum):
    TRADING = "TRADING"
    HALTED = "HALTED"
    LIMIT_UP = "LIMIT_UP"
    LIMIT_DOWN = "LIMIT_DOWN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


def require_aware_utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise MarketDataValidationError(f"{field_name} must be timezone-aware")
    if value.utcoffset() != timezone.utc.utcoffset(value):
        raise MarketDataValidationError(f"{field_name} must be stored in UTC")


def require_non_negative(value: Decimal | None, field_name: str) -> None:
    if value is not None and value < 0:
        raise MarketDataValidationError(f"{field_name} must be non-negative")


@dataclass(frozen=True, slots=True)
class MarketTick:
    schema_version: str
    symbol: str
    market_data_time: datetime
    ingest_time: datetime
    source: str
    source_sequence: str | None
    last_price: Decimal | None
    bid_price: Decimal | None
    ask_price: Decimal | None
    bid_size: Decimal | None
    ask_size: Decimal | None
    trade_price: Decimal | None
    trade_volume: Decimal | None
    trading_status: TradingStatus
    data_source_version: str
    source_revision: str | None = None

    def validate(self) -> None:
        for field_name in ("schema_version", "symbol", "source", "data_source_version"):
            if not str(getattr(self, field_name)).strip():
                raise MarketDataValidationError(f"{field_name} is required")

        require_aware_utc(self.market_data_time, "market_data_time")
        require_aware_utc(self.ingest_time, "ingest_time")
        for field_name in (
            "last_price",
            "bid_price",
            "ask_price",
            "bid_size",
            "ask_size",
            "trade_price",
            "trade_volume",
        ):
            require_non_negative(getattr(self, field_name), field_name)

    @property
    def identity_key(self) -> tuple[Any, ...]:
        if self.source_sequence:
            return (
                self.source,
                self.symbol,
                self.market_data_time,
                self.source_sequence,
                self.data_source_version,
            )

        return (
            self.source,
            self.symbol,
            self.market_data_time,
            self.last_price,
            self.trade_volume,
            self.data_source_version,
        )


@dataclass(frozen=True, slots=True)
class MarketBar:
    schema_version: str
    symbol: str
    timeframe: str
    bar_start_time: datetime
    bar_end_time: datetime
    market_data_time: datetime
    ingest_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal | None
    amount: Decimal | None
    turnover: Decimal | None
    trading_status: TradingStatus
    is_closed: bool
    bar_close_time: datetime
    source: str
    data_source_version: str
    as_of_version: str
    source_revision: str | None = None

    def validate(self, *, require_closed: bool = True) -> None:
        for field_name in (
            "schema_version",
            "symbol",
            "timeframe",
            "source",
            "data_source_version",
            "as_of_version",
        ):
            if not str(getattr(self, field_name)).strip():
                raise MarketDataValidationError(f"{field_name} is required")

        for field_name in (
            "bar_start_time",
            "bar_end_time",
            "market_data_time",
            "ingest_time",
            "bar_close_time",
        ):
            require_aware_utc(getattr(self, field_name), field_name)

        if self.bar_start_time >= self.bar_end_time:
            raise MarketDataValidationError("bar_start_time must be before bar_end_time")
        if self.market_data_time != self.bar_end_time:
            raise MarketDataValidationError("market_data_time must equal bar_end_time for MarketBar")
        if require_closed and not self.is_closed:
            raise MarketDataValidationError("only closed MarketBar objects can enter core workflows")
        if require_closed and self.bar_close_time > self.ingest_time:
            raise MarketDataValidationError("closed bar cannot be ingested before bar_close_time")

        for field_name in (
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "amount",
            "turnover",
        ):
            require_non_negative(getattr(self, field_name), field_name)

        highest_observed = max(self.open_price, self.close_price, self.low_price)
        lowest_observed = min(self.open_price, self.close_price, self.high_price)
        if self.high_price < highest_observed:
            raise MarketDataValidationError("high_price must be >= open/close/low")
        if self.low_price > lowest_observed:
            raise MarketDataValidationError("low_price must be <= open/close/high")

    @property
    def version_key(self) -> tuple[str, str, datetime, str, str]:
        return (
            self.symbol,
            self.timeframe,
            self.market_data_time,
            self.data_source_version,
            self.as_of_version,
        )

    @property
    def content_fingerprint(self) -> tuple[Any, ...]:
        return (
            self.open_price,
            self.high_price,
            self.low_price,
            self.close_price,
            self.volume,
            self.amount,
            self.turnover,
            self.trading_status,
            self.is_closed,
            self.source,
            self.source_revision,
        )

