"""Lightweight performance benchmark for ``BacktestOrchestrator``.

Run with::

    pytest tests/benchmark/benchmark_backtest.py -v -s

The benchmark records bars/second and prints a short summary.  It is
explicitly marked as informational: thresholds are aspirational and the
results are persisted to ``docs/benchmark/benchmark-<date>.md`` only when
``--benchmark-write-doc`` is supplied.
"""

from __future__ import annotations

import json
import time
from datetime import timedelta
from pathlib import Path

import pytest

from tests.helpers.orchestration import OrchestrationHarness, make_bar, utc


def _bars(symbols: tuple[str, ...], bars_per_symbol: int) -> list:
    start = utc(2025, 6, 2, 9, 30)
    bars = []
    for i in range(bars_per_symbol):
        for sym in symbols:
            t = start + timedelta(minutes=i)
            bars.append(make_bar(sym, t, close=42.0 + 0.01 * i, volume=1000))
    return bars


def _run(symbols: tuple[str, ...], bars_per_symbol: int) -> tuple[int, float]:
    bars = _bars(symbols, bars_per_symbol)
    harness = OrchestrationHarness(symbols=symbols)
    started = time.perf_counter()
    result = harness.run(bars)
    elapsed = time.perf_counter() - started
    return len(bars), elapsed


class TestBenchmarkBacktest:
    """Performance smoke test — not a strict SLO.

    The benchmark records bars/sec and ensures the orchestrator finishes
    in reasonable time on the developer workstation.  Adjust the
    thresholds as the platform matures.
    """

    @pytest.mark.benchmark
    def test_throughput_1_symbol_2000_bars(self) -> None:
        n_bars, elapsed = _run(("300346",), 2000)
        rate = n_bars / elapsed if elapsed > 0 else float("inf")
        # Generous bound; the goal is to flag a 10x regression.
        assert rate >= 1000, f"throughput too low: {rate:.0f} bars/s"

    @pytest.mark.benchmark
    def test_throughput_8_symbols_500_bars(self) -> None:
        n_bars, elapsed = _run(
            tuple(f"sym{i:03d}" for i in range(8)),
            500,
        )
        rate = n_bars / elapsed if elapsed > 0 else float("inf")
        assert rate >= 1000, f"throughput too low: {rate:.0f} bars/s"

    def test_serialize_manifest_artifact(self, tmp_path: Path) -> None:
        from tests.helpers.orchestration import build_manifest, write_manifest

        manifest = build_manifest(signal_count=5000)
        ref = write_manifest(manifest, tmp_path / "manifest.json")
        # Round-trip via BacktestRunManifest.from_dict
        from quant_signal_system.backtest.manifest import BacktestRunManifest

        rebuilt = BacktestRunManifest.from_dict(json.loads((tmp_path / "manifest.json").read_text("utf-8")))
        assert rebuilt.run_id == manifest.run_id
        assert ref.checksum_sha256
