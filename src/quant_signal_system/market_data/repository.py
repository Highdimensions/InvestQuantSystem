"""Append-only in-memory market data repository for tests and first adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Iterable

from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.market_data.quarantine import QuarantineRecord


class DuplicatePolicy(StrEnum):
    IDEMPOTENT = "IDEMPOTENT"
    CONFLICT_TO_QUARANTINE = "CONFLICT_TO_QUARANTINE"
    RAISE = "RAISE"


class VersionConflictError(ValueError):
    """Raised when a same-version bar attempts to overwrite old facts."""


@dataclass(slots=True)
class InMemoryMarketDataRepository:
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.RAISE
    _bars: dict[tuple[str, str, datetime, str, str], MarketBar] = field(default_factory=dict)
    _quarantine: list[QuarantineRecord] = field(default_factory=list)

    def save_bar(self, bar: MarketBar) -> str:
        bar.validate(require_closed=True)
        key = bar.version_key
        existing = self._bars.get(key)
        if existing is None:
            self._bars[key] = bar
            return "inserted"

        if existing.content_fingerprint == bar.content_fingerprint:
            return "duplicate"

        detail = "same version key has different OHLCV or metadata"
        if self.duplicate_policy == DuplicatePolicy.CONFLICT_TO_QUARANTINE:
            self._quarantine.append(
                QuarantineRecord(
                    provider=bar.source,
                    reason_code="VERSION_CONFLICT",
                    reason_detail=detail,
                    raw_payload={
                        "symbol": bar.symbol,
                        "timeframe": bar.timeframe,
                        "market_data_time": bar.market_data_time.isoformat(),
                        "data_source_version": bar.data_source_version,
                        "as_of_version": bar.as_of_version,
                    },
                    data_source_version=bar.data_source_version,
                    as_of_version=bar.as_of_version,
                )
            )
            return "quarantined"

        raise VersionConflictError(detail)

    def read_bars(
        self,
        *,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
        timeframe: str,
        data_source_version: str,
        as_of_version: str,
    ) -> list[MarketBar]:
        return sorted(
            (
                bar
                for key, bar in self._bars.items()
                if key[0] == symbol
                and key[1] == timeframe
                and from_time <= key[2] <= to_time
                and key[3] == data_source_version
                and key[4] == as_of_version
            ),
            key=lambda bar: bar.market_data_time,
        )

    def query_missing(
        self,
        *,
        symbol: str,
        timeframe: str,
        expected_times: Iterable[datetime],
        data_source_version: str,
        as_of_version: str,
    ) -> list[datetime]:
        missing: list[datetime] = []
        for market_data_time in expected_times:
            key = (symbol, timeframe, market_data_time, data_source_version, as_of_version)
            if key not in self._bars:
                missing.append(market_data_time)
        return missing

    def add_quarantine(self, record: QuarantineRecord) -> None:
        self._quarantine.append(record)

    @property
    def quarantine_records(self) -> tuple[QuarantineRecord, ...]:
        return tuple(self._quarantine)

