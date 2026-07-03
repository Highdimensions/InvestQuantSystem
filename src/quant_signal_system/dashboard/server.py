"""Local HTTP dashboard for research-only signal inspection."""

from __future__ import annotations

import argparse
import json
import mimetypes
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from quant_signal_system.dashboard.dto import (
    DashboardBar,
    DashboardEvaluationSummary,
    DashboardSignalPoint,
    dto_dict,
    json_ready,
)
from quant_signal_system.dashboard.shadow import ShadowRunManager
from quant_signal_system.market_data.sqlite_repository import SQLiteMarketDataRepository
from quant_signal_system.signals.sqlite_repository import SQLiteSignalRepository


@dataclass(frozen=True, slots=True)
class DashboardConfig:
    market_db: Path
    signal_db: Path
    host: str = "127.0.0.1"
    port: int = 8000
    static_dir: Path = Path(__file__).with_name("static")


@dataclass(slots=True)
class DashboardApp:
    config: DashboardConfig
    market_repository: SQLiteMarketDataRepository
    signal_repository: SQLiteSignalRepository
    shadow_runs: ShadowRunManager


def create_app(config: DashboardConfig) -> DashboardApp:
    config.market_db.parent.mkdir(parents=True, exist_ok=True)
    config.signal_db.parent.mkdir(parents=True, exist_ok=True)
    market_repository = SQLiteMarketDataRepository(config.market_db)
    signal_repository = SQLiteSignalRepository(config.signal_db)
    return DashboardApp(
        config=config,
        market_repository=market_repository,
        signal_repository=signal_repository,
        shadow_runs=ShadowRunManager(
            market_repository=market_repository,
            signal_repository=signal_repository,
        ),
    )


def run_dashboard(config: DashboardConfig) -> None:
    app = create_app(config)
    handler = _handler_factory(app)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    print(f"Dashboard running at http://{config.host}:{config.port}/")
    server.serve_forever()


def _handler_factory(app: DashboardApp) -> type[BaseHTTPRequestHandler]:
    class DashboardRequestHandler(BaseHTTPRequestHandler):
        server_version = "QuantSignalDashboard/0.1"

        def do_GET(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path.startswith("/api/"):
                    self._handle_api_get(parsed.path, parse_qs(parsed.query))
                    return
                self._serve_static(parsed.path)
            except Exception as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:  # noqa: N802
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/api/shadow-runs":
                    body = self._read_json()
                    state = app.shadow_runs.start_run(
                        symbol=str(body["symbol"]),
                        timeframe=str(body.get("timeframe", "1m")),
                        from_time=_parse_time(str(body["from_time"])),
                        to_time=_parse_time(str(body["to_time"])),
                        data_source_version=str(
                            body.get("data_source_version", "akshare-exploration-v1")
                        ),
                        as_of_version=str(body.get("as_of_version", "asof-research-v1")),
                    )
                    self._json(state.to_dict(), status=HTTPStatus.ACCEPTED)
                    return
                if parsed.path.startswith("/api/shadow-runs/") and parsed.path.endswith("/stop"):
                    run_id = parsed.path.split("/")[3]
                    self._json(app.shadow_runs.stop_run(run_id).to_dict())
                    return
                self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            except KeyError as exc:
                self._json({"error": f"missing field: {exc}"}, status=HTTPStatus.BAD_REQUEST)
            except Exception as exc:
                self._json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
            if path == "/api/health":
                self._json(
                    {
                        "status": "ok",
                        "scope": "research-only",
                        "real_trading": False,
                    }
                )
                return
            if path == "/api/bars":
                bars = app.market_repository.read_bars(
                    symbol=_required(query, "symbol"),
                    from_time=_parse_time(_required(query, "from_time")),
                    to_time=_parse_time(_required(query, "to_time")),
                    timeframe=_optional(query, "timeframe", "1m"),
                    data_source_version=_required(query, "data_source_version"),
                    as_of_version=_required(query, "as_of_version"),
                )
                self._json({"bars": [dto_dict(DashboardBar.from_bar(bar)) for bar in bars]})
                return
            if path == "/api/signals":
                signals = app.signal_repository.list_signals(
                    symbol=_optional(query, "symbol"),
                    from_time=_optional_time(query, "from_time"),
                    to_time=_optional_time(query, "to_time"),
                    strategy_versions=_csv(query, "strategy_version"),
                )
                directions = {item.upper() for item in _csv(query, "direction")}
                if directions:
                    signals = [
                        signal
                        for signal in signals
                        if DashboardSignalPoint.from_signal(signal).direction_label in directions
                    ]
                self._json(
                    {"signals": [dto_dict(DashboardSignalPoint.from_signal(signal)) for signal in signals]}
                )
                return
            if path == "/api/evaluations":
                signal_ids = _csv(query, "signal_id")
                has_signal_filters = any(
                    name in query for name in ("symbol", "from_time", "to_time", "strategy_version")
                )
                if not signal_ids:
                    signals = app.signal_repository.list_signals(
                        symbol=_optional(query, "symbol"),
                        from_time=_optional_time(query, "from_time"),
                        to_time=_optional_time(query, "to_time"),
                        strategy_versions=_csv(query, "strategy_version"),
                    )
                    signal_ids = tuple(signal.signal_id for signal in signals)
                    if has_signal_filters and not signal_ids:
                        self._json({"evaluations": []})
                        return
                evaluations = app.signal_repository.list_evaluations(signal_ids=tuple(signal_ids))
                self._json(
                    {
                        "evaluations": [
                            dto_dict(DashboardEvaluationSummary.from_evaluation(evaluation))
                            for evaluation in evaluations
                        ]
                    }
                )
                return
            if path == "/api/strategies":
                self._json({"strategies": json_ready(app.signal_repository.strategy_counts())})
                return
            if path == "/api/shadow-runs":
                self._json({"shadow_runs": app.shadow_runs.list_runs()})
                return
            self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

        def _serve_static(self, path: str) -> None:
            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.end_headers()
                return
            relative = "index.html" if path in {"", "/"} else path.lstrip("/")
            candidate = (app.config.static_dir / relative).resolve()
            static_root = app.config.static_dir.resolve()
            if static_root not in candidate.parents and candidate != static_root:
                self._json({"error": "invalid static path"}, status=HTTPStatus.BAD_REQUEST)
                return
            if not candidate.exists() or not candidate.is_file():
                self._json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
                return
            data = candidate.read_bytes()
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _json(self, payload: object, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(json_ready(payload), ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return DashboardRequestHandler


def _required(query: dict[str, list[str]], name: str) -> str:
    value = _optional(query, name)
    if value is None or value == "":
        raise ValueError(f"{name} is required")
    return value


def _optional(query: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = query.get(name)
    return default if not values else values[-1]


def _csv(query: dict[str, list[str]], name: str) -> tuple[str, ...]:
    values = query.get(name, [])
    items: list[str] = []
    for value in values:
        items.extend(part.strip() for part in value.split(",") if part.strip())
    return tuple(items)


def _optional_time(query: dict[str, list[str]], name: str) -> datetime | None:
    value = _optional(query, name)
    return None if value is None else _parse_time(value)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("time values must include timezone")
    return parsed.astimezone(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local research signal dashboard.")
    parser.add_argument("--market-db", type=Path, default=Path("reports/dashboard/market.db"))
    parser.add_argument("--signal-db", type=Path, default=Path("reports/dashboard/signals.db"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    run_dashboard(
        DashboardConfig(
            market_db=args.market_db,
            signal_db=args.signal_db,
            host=args.host,
            port=args.port,
        )
    )


if __name__ == "__main__":
    main()
