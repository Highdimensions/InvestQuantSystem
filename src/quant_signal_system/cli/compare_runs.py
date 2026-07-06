"""Compare two backtest manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Sequence

from quant_signal_system.backtest.manifest import BacktestRunManifest
from quant_signal_system.cli._common import (
    EXIT_OK,
    EXIT_USER_ERROR,
    EXIT_VALIDATION_FAILED,
    diff_dicts,
    parse_args,
)


def _manifest_summary(manifest: BacktestRunManifest) -> dict[str, object]:
    """Build a comparable summary of a manifest."""
    from datetime import datetime

    def _iso(value: object) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value) if value is not None else ""

    return {
        "run_id": manifest.run_id,
        "run_mode": manifest.run_mode,
        "run_status": manifest.run_status,
        "spec_hash": manifest.resolved_config_hash,
        "data_source_version": manifest.data_source_version,
        "as_of_version": manifest.as_of_version,
        "from_time": _iso(manifest.from_time),
        "to_time": _iso(manifest.to_time),
        "strategy_versions": sorted(manifest.strategy_versions),
        "feature_versions": sorted(manifest.feature_versions),
        "cost_model_version": manifest.cost_model_version,
        "fill_model_version": manifest.fill_model_version,
        "total_bars_processed": manifest.total_bars_processed,
        "total_signals_generated": manifest.total_signals_generated,
        "total_fills": manifest.total_fills,
    }


def compare(manifest_a: BacktestRunManifest, manifest_b: BacktestRunManifest) -> dict[str, object]:
    """Return a structured diff between two manifests."""
    summary_a = _manifest_summary(manifest_a)
    summary_b = _manifest_summary(manifest_b)
    diffs = diff_dicts(summary_a, summary_b)
    return {
        "run_id_a": summary_a["run_id"],
        "run_id_b": summary_b["run_id"],
        "differences": diffs,
        "comparable": "spec_hash" not in diffs,
    }


def render_diff(diff: Mapping[str, object]) -> str:
    """Render a diff dict as a human-readable summary."""
    if not diff.get("differences"):
        return f"No differences between {diff.get('run_id_a')} and {diff.get('run_id_b')}."
    lines = [f"Differences between {diff['run_id_a']} and {diff['run_id_b']}:"]
    for key, (left, right) in diff["differences"].items():
        lines.append(f"- {key}: {left!r} -> {right!r}")
    return "\n".join(lines)


def cli(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `compare_runs`."""
    args = parse_args(
        argv if argv is not None else __import__("sys").argv[1:],
        description="Compare two backtest runs.",
    )
    if not args.run_id_a or not args.run_id_b:
        print("[user-error] --run-id-a and --run-id-b are required", file=__import__("sys").stderr)
        return EXIT_USER_ERROR
    if not args.artifact_dir:
        print("[user-error] --artifact-dir is required (base path for runs)", file=__import__("sys").stderr)
        return EXIT_USER_ERROR

    base = Path(args.artifact_dir)
    path_a = base / args.run_id_a / "manifest.json"
    path_b = base / args.run_id_b / "manifest.json"
    if not path_a.exists():
        print(f"[validation-failed] manifest A not found: {path_a}", flush=True)
        return EXIT_VALIDATION_FAILED
    if not path_b.exists():
        print(f"[validation-failed] manifest B not found: {path_b}", flush=True)
        return EXIT_VALIDATION_FAILED

    from quant_signal_system.cli._common import load_manifest

    diff = compare(load_manifest(path_a), load_manifest(path_b))
    print(json.dumps(diff, indent=2, ensure_ascii=False), flush=True)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(cli())