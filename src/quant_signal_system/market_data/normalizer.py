"""Normalize raw provider OHLCV rows into internal MarketBar contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Mapping

from quant_signal_system.config.data_source import DataSourceProfile
from quant_signal_system.contracts.market import (
    MarketBar,
    MarketDataValidationError,
    TradingStatus,
)
from quant_signal_system.market_data.quarantine import QuarantineRecord


@dataclass(frozen=True, slots=True)
class BarFieldMap:
    symbol: str = "symbol"
    bar_end_time: str = "bar_end_time"
    open_price: str = "open"
    high_price: str = "high"
    low_price: str = "low"
    close_price: str = "close"
    volume: str = "volume"
    amount: str = "amount"
    turnover: str = "turnover"
    trading_status: str = "trading_status"
    source_revision: str = "source_revision"


AKSHARE_A_SHARE_FIELD_MAP = BarFieldMap(
    symbol="股票代码",
    bar_end_time="时间",
    open_price="开盘",
    high_price="最高",
    low_price="最低",
    close_price="收盘",
    volume="成交量",
    amount="成交额",
    turnover="换手率",
    trading_status="交易状态",
)


TUSHARE_A_SHARE_FIELD_MAP = BarFieldMap(
    symbol="ts_code",
    bar_end_time="trade_time",
    open_price="open",
    high_price="high",
    low_price="low",
    close_price="close",
    volume="vol",
    amount="amount",
    trading_status="trading_status",
)


class BarNormalizer:
    """Convert provider rows to closed, UTC, versioned MarketBar objects."""

    schema_version = "market-bar-v1"

    def normalize_raw_bar(
        self,
        raw: Mapping[str, object],
        *,
        profile: DataSourceProfile,
        field_map: BarFieldMap,
        ingest_time: datetime,
    ) -> MarketBar:
        profile.validate()
        try:
            bar_end_time = self._parse_time(raw[field_map.bar_end_time])
            timeframe = profile.frequency
            bar_start_time = self._infer_bar_start(bar_end_time, timeframe)
            status = self._parse_status(raw.get(field_map.trading_status))
            bar = MarketBar(
                schema_version=self.schema_version,
                symbol=str(raw[field_map.symbol]).strip(),
                timeframe=timeframe,
                bar_start_time=bar_start_time,
                bar_end_time=bar_end_time,
                market_data_time=bar_end_time,
                ingest_time=ingest_time,
                open_price=self._decimal(raw[field_map.open_price], "open_price"),
                high_price=self._decimal(raw[field_map.high_price], "high_price"),
                low_price=self._decimal(raw[field_map.low_price], "low_price"),
                close_price=self._decimal(raw[field_map.close_price], "close_price"),
                volume=self._optional_decimal(raw.get(field_map.volume), "volume"),
                amount=self._optional_decimal(raw.get(field_map.amount), "amount"),
                turnover=self._optional_decimal(raw.get(field_map.turnover), "turnover"),
                trading_status=status,
                is_closed=True,
                bar_close_time=bar_end_time,
                source=profile.provider,
                data_source_version=profile.data_source_version,
                as_of_version=profile.as_of_version,
                source_revision=self._optional_text(raw.get(field_map.source_revision)),
            )
            bar.validate(require_closed=True)
            return bar
        except KeyError as exc:
            raise MarketDataValidationError(f"missing provider field: {exc.args[0]}") from exc

    def quarantine_raw_bar(
        self,
        raw: Mapping[str, object],
        *,
        profile: DataSourceProfile,
        field_map: BarFieldMap,
        ingest_time: datetime,
    ) -> MarketBar | QuarantineRecord:
        try:
            return self.normalize_raw_bar(
                raw,
                profile=profile,
                field_map=field_map,
                ingest_time=ingest_time,
            )
        except Exception as exc:
            return QuarantineRecord(
                provider=profile.provider,
                reason_code="NORMALIZATION_FAILED",
                reason_detail=str(exc),
                raw_payload=dict(raw),
                data_source_version=profile.data_source_version,
                as_of_version=profile.as_of_version,
            )

    def _parse_time(self, value: object) -> datetime:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value))

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise MarketDataValidationError("provider time must include timezone before UTC storage")
        return parsed.astimezone(timezone.utc)

    def _infer_bar_start(self, bar_end_time: datetime, timeframe: str) -> datetime:
        if timeframe.endswith("m") and timeframe[:-1].isdigit():
            return bar_end_time - timedelta(minutes=int(timeframe[:-1]))
        if timeframe.endswith("d") and timeframe[:-1].isdigit():
            return bar_end_time - timedelta(days=int(timeframe[:-1]))
        raise MarketDataValidationError(f"unsupported timeframe: {timeframe}")

    def _decimal(self, value: object, field_name: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise MarketDataValidationError(f"{field_name} must be decimal-compatible") from exc

    def _optional_decimal(self, value: object, field_name: str) -> Decimal | None:
        if value in (None, ""):
            return None
        return self._decimal(value, field_name)

    def _optional_text(self, value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    def _parse_status(self, value: object) -> TradingStatus:
        if value in (None, ""):
            return TradingStatus.UNKNOWN
        text = str(value).strip().upper()
        aliases = {
            "交易": TradingStatus.TRADING,
            "正常": TradingStatus.TRADING,
            "停牌": TradingStatus.HALTED,
            "涨停": TradingStatus.LIMIT_UP,
            "跌停": TradingStatus.LIMIT_DOWN,
        }
        return aliases.get(text, TradingStatus.__members__.get(text, TradingStatus.UNKNOWN))

