from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import urlopen
import json

from quant_signal_system.backtest.runner import BacktestRunner
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.dashboard.server import DashboardConfig, _handler_factory, create_app
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies.composer import StrategyComposer
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.time.clock import FrozenClock


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def bar(time_value: str, close: str, volume: str = "100") -> MarketBar:
    end = utc(time_value)
    price = Decimal(close)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=end - timedelta(minutes=1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=price,
        high_price=price + Decimal("0.10"),
        low_price=price - Decimal("0.10"),
        close_price=price,
        volume=Decimal(volume),
        amount=price * Decimal(volume),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source="AKShare",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def get_json(base_url: str, path: str) -> dict:
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_status(base_url: str, path: str) -> int:
    with urlopen(f"{base_url}{path}", timeout=5) as response:
        return response.status


def test_dashboard_api_serves_bars_strategies_and_signals(tmp_path) -> None:
    app = create_app(
        DashboardConfig(
            market_db=tmp_path / "market.db",
            signal_db=tmp_path / "signals.db",
            host="127.0.0.1",
            port=0,
        )
    )
    clock = FrozenClock(utc("2024-07-03T01:35:00+00:00"))
    bars = [
        bar("2024-07-03T01:31:00+00:00", "10.00", "100"),
        bar("2024-07-03T01:32:00+00:00", "10.10", "100"),
        bar("2024-07-03T01:33:00+00:00", "10.30", "300"),
    ]
    for item in bars:
        app.market_repository.save_bar(item)

    result = BacktestRunner(
        RollingFeatureEngine(clock=clock),
        StrategyComposer.single(RuleStrategyRuntime()),
        SignalService(clock),
        app.signal_repository,
    ).run_bars(bars)
    assert result.signals_created == 1

    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_factory(app))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        strategies = get_json(base_url, "/api/strategies")
        assert strategies["strategies"][0]["strategy_version"] == "baseline-rules-v1"

        bars_payload = get_json(
            base_url,
            "/api/bars?symbol=000001&timeframe=1m"
            "&from_time=2024-07-03T01:31:00%2B00:00"
            "&to_time=2024-07-03T01:33:00%2B00:00"
            "&data_source_version=akshare-exploration-v1"
            "&as_of_version=asof-research-v1",
        )
        assert len(bars_payload["bars"]) == 3

        signals = get_json(
            base_url,
            "/api/signals?symbol=000001"
            "&from_time=2024-07-03T01:31:00%2B00:00"
            "&to_time=2024-07-03T01:35:00%2B00:00"
            "&strategy_version=baseline-rules-v1",
        )
        assert len(signals["signals"]) == 1
        assert signals["signals"][0]["direction_label"] == "BUY"
        assert signals["signals"][0]["feature_version"] == "rolling-feature-v1"

        health = get_json(base_url, "/api/health")
        assert health["real_trading"] is False
        assert get_status(base_url, "/favicon.ico") == 204
    finally:
        server.shutdown()
        thread.join(timeout=5)
