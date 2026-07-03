"""SQLite-backed append-only market data repository."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.market_data.quarantine import QuarantineRecord
from quant_signal_system.market_data.repository import VersionConflictError


@dataclass(slots=True)
class SQLiteMarketDataRepository:
    database_path: str | Path

    def __post_init__(self) -> None:
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.database_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _initialise(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    market_data_time TEXT NOT NULL,
                    data_source_version TEXT NOT NULL,
                    as_of_version TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    bar_start_time TEXT NOT NULL,
                    bar_end_time TEXT NOT NULL,
                    ingest_time TEXT NOT NULL,
                    open_price TEXT NOT NULL,
                    high_price TEXT NOT NULL,
                    low_price TEXT NOT NULL,
                    close_price TEXT NOT NULL,
                    volume TEXT,
                    amount TEXT,
                    turnover TEXT,
                    trading_status TEXT NOT NULL,
                    is_closed INTEGER NOT NULL,
                    bar_close_time TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_revision TEXT,
                    PRIMARY KEY (
                        symbol, timeframe, market_data_time,
                        data_source_version, as_of_version
                    )
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS market_data_quarantine (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    reason_detail TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    data_source_version TEXT NOT NULL,
                    as_of_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def save_bar(self, bar: MarketBar) -> str:
        bar.validate(require_closed=True)
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT * FROM market_bars
                WHERE symbol = ? AND timeframe = ? AND market_data_time = ?
                  AND data_source_version = ? AND as_of_version = ?
                """,
                (
                    bar.symbol,
                    bar.timeframe,
                    bar.market_data_time.isoformat(),
                    bar.data_source_version,
                    bar.as_of_version,
                ),
            ).fetchone()
            if existing is not None:
                stored = self._row_to_bar(existing)
                if stored.content_fingerprint == bar.content_fingerprint:
                    return "duplicate"
                raise VersionConflictError("same version key has different market bar content")

            conn.execute(
                """
                INSERT INTO market_bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._bar_values(bar),
            )
            return "inserted"

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
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM market_bars
                WHERE symbol = ? AND timeframe = ?
                  AND market_data_time >= ? AND market_data_time <= ?
                  AND data_source_version = ? AND as_of_version = ?
                ORDER BY market_data_time ASC
                """,
                (
                    symbol,
                    timeframe,
                    from_time.isoformat(),
                    to_time.isoformat(),
                    data_source_version,
                    as_of_version,
                ),
            ).fetchall()
        return [self._row_to_bar(row) for row in rows]

    def add_quarantine(self, record: QuarantineRecord) -> None:
        import json

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_data_quarantine (
                    provider, reason_code, reason_detail, raw_payload,
                    data_source_version, as_of_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.provider,
                    record.reason_code,
                    record.reason_detail,
                    json.dumps(dict(record.raw_payload), ensure_ascii=False, default=str),
                    record.data_source_version,
                    record.as_of_version,
                    record.created_at.isoformat(),
                ),
            )

    def _bar_values(self, bar: MarketBar) -> tuple[object, ...]:
        return (
            bar.symbol,
            bar.timeframe,
            bar.market_data_time.isoformat(),
            bar.data_source_version,
            bar.as_of_version,
            bar.schema_version,
            bar.bar_start_time.isoformat(),
            bar.bar_end_time.isoformat(),
            bar.ingest_time.isoformat(),
            str(bar.open_price),
            str(bar.high_price),
            str(bar.low_price),
            str(bar.close_price),
            None if bar.volume is None else str(bar.volume),
            None if bar.amount is None else str(bar.amount),
            None if bar.turnover is None else str(bar.turnover),
            bar.trading_status.value,
            int(bar.is_closed),
            bar.bar_close_time.isoformat(),
            bar.source,
            bar.source_revision,
        )

    def _row_to_bar(self, row: sqlite3.Row) -> MarketBar:
        def optional_decimal(value: str | None) -> Decimal | None:
            return None if value is None else Decimal(value)

        return MarketBar(
            schema_version=row["schema_version"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            bar_start_time=datetime.fromisoformat(row["bar_start_time"]),
            bar_end_time=datetime.fromisoformat(row["bar_end_time"]),
            market_data_time=datetime.fromisoformat(row["market_data_time"]),
            ingest_time=datetime.fromisoformat(row["ingest_time"]),
            open_price=Decimal(row["open_price"]),
            high_price=Decimal(row["high_price"]),
            low_price=Decimal(row["low_price"]),
            close_price=Decimal(row["close_price"]),
            volume=optional_decimal(row["volume"]),
            amount=optional_decimal(row["amount"]),
            turnover=optional_decimal(row["turnover"]),
            trading_status=TradingStatus(row["trading_status"]),
            is_closed=bool(row["is_closed"]),
            bar_close_time=datetime.fromisoformat(row["bar_close_time"]),
            source=row["source"],
            data_source_version=row["data_source_version"],
            as_of_version=row["as_of_version"],
            source_revision=row["source_revision"],
        )

