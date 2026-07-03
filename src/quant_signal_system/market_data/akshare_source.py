"""AKShare-backed A-share market data adapter.

The adapter maps AKShare's provider-specific Chinese columns into the internal
MarketBar contract. It does not expose AKShare objects to strategy, feature, or
evaluation code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from importlib import import_module
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from quant_signal_system.config.data_source import DataSourceProfile, akshare_exploration_profile
from quant_signal_system.contracts.market import MarketBar, MarketDataValidationError
from quant_signal_system.market_data.normalizer import AKSHARE_A_SHARE_FIELD_MAP, BarNormalizer
from quant_signal_system.market_data.quarantine import QuarantineRecord


AKSHARE_MINUTE_PERIODS = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "60m": "60",
}

AKSHARE_DAILY_PERIODS = {"1d": "daily", "daily": "daily"}

AKSHARE_ADJUSTMENT = {
    "none": "",
    "": "",
    "qfq": "qfq",
    "hfq": "hfq",
}


@dataclass(slots=True)
class AKShareMarketDataSource:
    """Read A-share bars from AKShare and normalize them to MarketBar.

    Parameters
    ----------
    profile:
        Versioned profile used for all bars emitted by this adapter.
    akshare_client:
        Optional injected client/module for tests. When omitted, `akshare` is
        imported lazily so the rest of the system can run without AKShare.
    market_timezone:
        AKShare A-share timestamps are interpreted as local exchange time when
        returned without timezone information, then stored as UTC internally.
    """

    profile: DataSourceProfile = field(default_factory=akshare_exploration_profile)
    normalizer: BarNormalizer = field(default_factory=BarNormalizer)
    akshare_client: object | None = None
    market_timezone: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Shanghai"))

    def read(
        self,
        *,
        symbols: Sequence[str],
        from_time: datetime,
        to_time: datetime,
    ) -> Iterable[MarketBar]:
        if from_time.tzinfo is None or to_time.tzinfo is None:
            raise MarketDataValidationError("from_time and to_time must be timezone-aware")
        if from_time > to_time:
            raise MarketDataValidationError("from_time must be <= to_time")

        client = self._client()
        for symbol in symbols:
            rows = self._fetch_rows(client, symbol=symbol, from_time=from_time, to_time=to_time)
            for raw in rows:
                try:
                    canonical = self._canonical_row(raw, symbol=symbol)
                except Exception:
                    continue
                normalized = self.normalizer.quarantine_raw_bar(
                    canonical,
                    profile=self.profile,
                    field_map=AKSHARE_A_SHARE_FIELD_MAP,
                    ingest_time=datetime.now(timezone.utc),
                )
                if isinstance(normalized, QuarantineRecord):
                    continue
                if from_time <= normalized.market_data_time <= to_time:
                    yield normalized

    def read_with_quarantine(
        self,
        *,
        symbols: Sequence[str],
        from_time: datetime,
        to_time: datetime,
    ) -> Iterable[MarketBar | QuarantineRecord]:
        if from_time.tzinfo is None or to_time.tzinfo is None:
            raise MarketDataValidationError("from_time and to_time must be timezone-aware")
        if from_time > to_time:
            raise MarketDataValidationError("from_time must be <= to_time")

        client = self._client()
        for symbol in symbols:
            rows = self._fetch_rows(client, symbol=symbol, from_time=from_time, to_time=to_time)
            for raw in rows:
                try:
                    canonical = self._canonical_row(raw, symbol=symbol)
                except Exception as exc:
                    yield QuarantineRecord(
                        provider=self.profile.provider,
                        reason_code="NORMALIZATION_FAILED",
                        reason_detail=str(exc),
                        raw_payload=dict(raw),
                        data_source_version=self.profile.data_source_version,
                        as_of_version=self.profile.as_of_version,
                    )
                    continue

                result = self.normalizer.quarantine_raw_bar(
                    canonical,
                    profile=self.profile,
                    field_map=AKSHARE_A_SHARE_FIELD_MAP,
                    ingest_time=datetime.now(timezone.utc),
                )
                if isinstance(result, MarketBar) and not (
                    from_time <= result.market_data_time <= to_time
                ):
                    continue
                yield result

    def _client(self) -> object:
        if self.akshare_client is not None:
            return self.akshare_client
        try:
            return import_module("akshare")
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "AKShare is not installed. Install with "
                "`python -m pip install -r requirements-akshare.txt`."
            ) from exc

    def _fetch_rows(
        self,
        client: object,
        *,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
    ) -> list[Mapping[str, object]]:
        frequency = self.profile.frequency
        ak_symbol = self._akshare_symbol(symbol)
        adjust = self._akshare_adjustment()

        if frequency in AKSHARE_MINUTE_PERIODS:
            data_frame = client.stock_zh_a_hist_min_em(
                symbol=ak_symbol,
                start_date=self._format_minute_time(from_time),
                end_date=self._format_minute_time(to_time),
                period=AKSHARE_MINUTE_PERIODS[frequency],
                adjust=adjust,
            )
        elif frequency in AKSHARE_DAILY_PERIODS:
            data_frame = client.stock_zh_a_hist(
                symbol=ak_symbol,
                period=AKSHARE_DAILY_PERIODS[frequency],
                start_date=self._format_daily_date(from_time),
                end_date=self._format_daily_date(to_time),
                adjust=adjust,
            )
        else:
            raise MarketDataValidationError(f"unsupported AKShare frequency: {frequency}")

        return self._rows_from_dataframe(data_frame)

    def _canonical_row(self, raw: Mapping[str, object], *, symbol: str) -> dict[str, object]:
        bar_time = self._provider_bar_time(raw)
        return {
            "股票代码": raw.get("股票代码") or self._akshare_symbol(symbol),
            "时间": self._local_market_time_to_utc_iso(bar_time),
            "开盘": self._first_present(raw, "开盘", "open"),
            "最高": self._first_present(raw, "最高", "high"),
            "最低": self._first_present(raw, "最低", "low"),
            "收盘": self._first_present(raw, "收盘", "close", "最新价"),
            "成交量": self._first_present(raw, "成交量", "volume", default=None),
            "成交额": self._first_present(raw, "成交额", "amount", default=None),
            "换手率": self._first_present(raw, "换手率", "turnover", default=None),
            "交易状态": self._first_present(raw, "交易状态", default="交易"),
            "source_revision": raw.get("source_revision"),
        }

    def _provider_bar_time(self, raw: Mapping[str, object]) -> object:
        if "时间" in raw:
            return raw["时间"]
        if "日期" in raw:
            return raw["日期"]
        raise MarketDataValidationError("AKShare row missing 时间 or 日期")

    def _local_market_time_to_utc_iso(self, value: object) -> str:
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            if len(text) == 10 and text[4] == "-" and text[7] == "-":
                parsed = datetime.combine(datetime.fromisoformat(text).date(), time(15, 0))
            else:
                parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=self.market_timezone)
        return parsed.astimezone(timezone.utc).isoformat()

    def _first_present(
        self,
        raw: Mapping[str, object],
        *names: str,
        default: object = ...,
    ) -> object:
        for name in names:
            if name in raw:
                return raw[name]
        if default is not ...:
            return default
        joined = ", ".join(names)
        raise MarketDataValidationError(f"AKShare row missing expected field: {joined}")

    def _rows_from_dataframe(self, data_frame: object) -> list[Mapping[str, object]]:
        if hasattr(data_frame, "to_dict"):
            rows = data_frame.to_dict(orient="records")
        else:
            rows = data_frame

        if rows is None:
            return []
        return [dict(row) for row in rows]

    def _akshare_symbol(self, symbol: str) -> str:
        text = symbol.strip().upper()
        if "." in text:
            text = text.split(".", 1)[0]
        if text.startswith(("SH", "SZ", "BJ")):
            text = text[2:]
        if not text.isdigit() or len(text) != 6:
            raise MarketDataValidationError(f"invalid A-share symbol for AKShare: {symbol}")
        return text

    def _akshare_adjustment(self) -> str:
        try:
            return AKSHARE_ADJUSTMENT[self.profile.adjustment]
        except KeyError as exc:
            raise MarketDataValidationError(
                f"unsupported AKShare adjustment: {self.profile.adjustment}"
            ) from exc

    def _format_minute_time(self, value: datetime) -> str:
        return value.astimezone(self.market_timezone).strftime("%Y-%m-%d %H:%M:%S")

    def _format_daily_date(self, value: datetime) -> str:
        return value.astimezone(self.market_timezone).strftime("%Y%m%d")
