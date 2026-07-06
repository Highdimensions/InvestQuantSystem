"""Artifact writers for backtest outputs."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


class _Encoder(json.JSONEncoder):
    def default(self, o: object) -> object:
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if is_dataclass(o):
            return asdict(o)
        return super().default(o)


def _to_json(obj: object) -> str:
    return json.dumps(obj, cls=_Encoder, indent=2, ensure_ascii=False)


def write_manifest(path: Path, data: dict) -> None:
    """Write manifest.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_json(data), encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    """Write a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_json(data), encoding="utf-8")


def write_report(path: Path, content: str) -> None:
    """Write report.md."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_parquet_fallback(path: Path, rows: list[dict]) -> None:
    """Write rows as JSONL (fallback when pyarrow is unavailable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_to_json(row) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
