"""Sina Finance-backed A-share market data adapter.

Uses Sina's KLine API for minute-level historical data.
API: https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import requests

from quant_signal_system.config.data_source import DataSourceProfile, akshare_exploration_profile
from quant_signal_system.contracts.market import MarketBar, MarketDataValidationError
from quant_signal_system.market_data.normalizer import BarFieldMap, BarNormalizer
from quant_signal_system.market_data.quarantine import QuarantineRecord


# Period to scale mapping for Sina API
SINA_SCALE_MAP = {
    "1m": 5,   # Sina minimum is 5 minutes
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "60m": 60,
    "1d": 240,
    "daily": 240,
}


# Sina field mapping
SINA_FIELD_MAP = BarFieldMap(
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
    source_revision="source_revision",
)


@dataclass(slots=True)
class SinaMarketDataSource:
    """Read A-share bars from Sina Finance KLine API.

    Sina provides historical K-line data through their quotes API.
    The minimum granularity is 5 minutes.
    """

    profile: DataSourceProfile = field(default_factory=akshare_exploration_profile)
    normalizer: BarNormalizer = field(default_factory=BarNormalizer)
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

        for symbol in symbols:
            rows = self._fetch_rows(symbol=symbol, from_time=from_time, to_time=to_time)
            for raw in rows:
                try:
                    canonical = self._canonical_row(raw, symbol=symbol)
                except Exception:
                    continue
                normalized = self.normalizer.quarantine_raw_bar(
                    canonical,
                    profile=self.profile,
                    field_map=SINA_FIELD_MAP,
                    ingest_time=datetime.now(timezone.utc),
                )
                if isinstance(normalized, QuarantineRecord):
                    continue
                if from_time <= normalized.market_data_time <= to_time:
                    yield normalized

    def _fetch_rows(
        self,
        *,
        symbol: str,
        from_time: datetime,
        to_time: datetime,
    ) -> list[Mapping[str, object]]:
        """Fetch data from Sina KLine API."""
        sina_symbol = self._sina_symbol(symbol)
        scale = SINA_SCALE_MAP.get(self.profile.frequency, 5)

        # Calculate how many bars to fetch (approximately)
        # Sina's datalen parameter limits the number of bars
        delta = to_time - from_time
        total_minutes = delta.total_seconds() / 60
        # For safety, fetch a reasonable number of bars
        if scale >= 60:
            datalen = min(int(total_minutes / scale) + 10, 800)
        else:
            datalen = min(int(total_minutes / scale) + 10, 300)

        url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
        params = {
            "symbol": sina_symbol,
            "scale": str(scale),
            "datalen": str(datalen),
            "ma": "no",  # Don't include moving averages
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            response.encoding = "utf-8"
            return self._parse_sina_kline(response.text, symbol)
        except Exception as e:
            raise MarketDataValidationError(f"Failed to fetch from Sina: {e}") from e

    def _parse_sina_kline(self, text: str, symbol: str) -> list[dict]:
        """Parse Sina's JSON K-line response."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Sina sometimes returns malformed JSON
            return []

        rows = []
        for item in data:
            if isinstance(item, dict) and "day" in item:
                rows.append({
                    "股票代码": symbol,
                    "时间": item["day"],
                    "开盘": float(item["open"]) if item.get("open") else 0,
                    "最高": float(item["high"]) if item.get("high") else 0,
                    "最低": float(item["low"]) if item.get("low") else 0,
                    "收盘": float(item["close"]) if item.get("close") else 0,
                    "成交量": float(item["volume"]) if item.get("volume") else 0,
                })
        return rows

    def _sina_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Sina format."""
        text = symbol.strip().upper()
        if "." in text:
            text = text.split(".", 1)[0]
        if text.startswith(("SH", "SZ", "BJ")):
            text = text[2:]

        # Determine prefix based on symbol range
        if text.startswith(("6",)):
            return f"sh{text}"
        elif text.startswith(("0", "3")):
            return f"sz{text}"
        else:
            return f"sz{text}"

    def _canonical_row(self, raw: Mapping[str, object], *, symbol: str) -> dict[str, object]:
        bar_time = self._provider_bar_time(raw)
        return {
            "股票代码": raw.get("股票代码") or self._sina_symbol(symbol),
            "时间": self._local_market_time_to_utc_iso(bar_time),
            "开盘": raw.get("开盘") or raw.get("open", 0),
            "最高": raw.get("最高") or raw.get("high", 0),
            "最低": raw.get("最低") or raw.get("low", 0),
            "收盘": raw.get("收盘") or raw.get("close", 0),
            "成交量": raw.get("成交量") or raw.get("volume", 0),
            "source_revision": None,
        }

    def _provider_bar_time(self, raw: Mapping[str, object]) -> object:
        if "时间" in raw:
            return raw["时间"]
        if "day" in raw:
            return raw["day"]
        if "日期" in raw:
            return raw["日期"]
        raise MarketDataValidationError("Sina row missing 时间/day/日期")

    def _local_market_time_to_utc_iso(self, value: object) -> str:
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            # Handle formats like "2026-07-10 14:15:00"
            if " " in text and ":" in text:
                parsed = datetime.fromisoformat(text)
            elif len(text) == 10 and text[4] == "-":
                parsed = datetime.combine(datetime.fromisoformat(text).date(), time(15, 0))
            else:
                parsed = datetime.fromisoformat(text)

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=self.market_timezone)
        return parsed.astimezone(timezone.utc).isoformat()
