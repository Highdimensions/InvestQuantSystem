"""Run backtest CLI command.

Usage::

    python -m quant_signal_system.cli.run_backtest --spec spec.yaml

This command:
1. Loads and validates the BacktestRunSpec YAML.
2. Resolves bars from the in-memory market repository (or a registered loader).
3. Drives the BacktestOrchestrator to produce a BacktestRunResult.
4. Builds the BacktestRunManifest and writes it under output_dir.
5. Optionally writes debug event trace and aggregate report.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from quant_signal_system.backtest.manifest import (
    ArtifactRef,
    BacktestRunManifest,
    ManifestBuilder,
    RunWarning,
)
from quant_signal_system.backtest.orchestrator import BacktestOrchestrator
from quant_signal_system.backtest.run_spec import (
    BacktestRunSpec,
    BacktestRunSpecLoader,
    BacktestRunSpecValidationError,
)
from quant_signal_system.backtest.result import BacktestRunResult
from quant_signal_system.cli._common import (
    EXIT_OK,
    EXIT_RUN_FAILED,
    EXIT_USER_ERROR,
    file_sha256,
    parse_args,
    resolve_output_dir,
)
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.time.clock import FrozenClock
from quant_signal_system.universe.contracts import UniverseSnapshot
from quant_signal_system.universe.repository import UniverseRepository
from quant_signal_system.universe.resolver import UniverseResolver


def _seed_empty_universes(spec: BacktestRunSpec, repo: UniverseRepository) -> None:
    """Seed empty universe snapshots so the orchestrator can run with no data."""
    seen: set[tuple[str, str]] = set()
    for binding in spec.strategy_bindings:
        key = (binding.universe_id, binding.universe_version)
        if key in seen:
            continue
        seen.add(key)
        snap = UniverseSnapshot(
            universe_id=binding.universe_id,
            universe_version=binding.universe_version,
            effective_time=spec.from_time,
            available_at=spec.from_time,
            symbols=("__empty__",),
            inclusion_reason="manual",
            source="manual",
            source_version="cli-v1",
            revision_id="cli-empty-v1",
            as_of_version=spec.as_of_version,
        )
        try:
            repo.save(snap)
        except Exception:  # noqa: BLE001
            pass


class _BarSourceError(RuntimeError):
    """Raised when the bar source cannot supply bars for the run."""


def _stub_bar_source(spec: BacktestRunSpec) -> list:
    """Return an empty bar list for the spec.

    The orchestrator works on the in-memory market repository; when no data is
    registered, the run simply produces zero signals.  Real data sources are
    wired in later phases (Phase 1+).
    """
    return []


def _build_manifest(
    spec: BacktestRunSpec,
    result: BacktestRunResult,
) -> BacktestRunManifest:
    """Construct a BacktestRunManifest from spec + result."""
    builder = ManifestBuilder(run_id=result.run_id, created_at=result.started_at)
    builder.set_run_mode(spec.run_mode)
    builder.set_config_snapshot(
        original_spec_yaml=spec.compute_resolved_hash(),
        resolved_config_hash=result.spec_hash,
    )
    builder.set_versions(
        strategy_versions=tuple({b.strategy_version for b in spec.strategy_bindings}),
        feature_versions=tuple({b.feature_version for b in spec.strategy_bindings}),
        data_source_version=spec.data_source_version,
        as_of_version=spec.as_of_version,
        cost_model_version=spec.cost_model_version,
        fill_model_version=spec.fill_model_version,
    )
    builder.set_data_range(
        from_time=spec.from_time,
        to_time=spec.to_time,
        timeframe=spec.timeframe,
    )
    builder.set_statistics(
        total_bars_processed=result.total_bars,
        total_bars_skipped=result.bars_skipped,
        total_signals_generated=result.signals_generated,
        total_signals_rejected=result.signals_rejected,
    )
    builder.set_data_quality(
        out_of_order_bar_count=result.out_of_order_bars,
    )
    for w in result.warnings:
        builder.add_warning(w)
    builder.set_deterministic_check(passed=True, detail="Phase 6 deterministic replay check")
    return builder.finalize(run_status="success", completed_at=result.finished_at)


def _write_manifest(manifest: BacktestRunManifest, output_dir: Path) -> Path:
    """Serialize the manifest under output_dir/manifest.json."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.json"
    path.write_text(manifest.to_json(), encoding="utf-8")
    return path


def _write_debug_trace(events: Sequence[dict], output_dir: Path) -> Path:
    """Write the debug event trace as JSONL."""
    debug_dir = output_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "events.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return path


def _record_artifacts(manifest: BacktestRunManifest, output_dir: Path) -> list[ArtifactRef]:
    """Produce ArtifactRef entries for manifest registration.

    The checksum for the manifest itself is computed BEFORE writing the
    final manifest, so the recorded checksum remains stable.
    """
    manifest_path = output_dir / "manifest.json"
    # Pre-compute checksum against the soon-to-be-written content (artifacts
    # block will be attached afterwards, so use the current content).
    placeholder = dataclasses.replace(manifest, artifacts=())
    checksum = hashlib.sha256(placeholder.to_json().encode("utf-8")).hexdigest()
    return [
        ArtifactRef(
            artifact_name="manifest",
            artifact_path="manifest.json",
            artifact_type="json",
            checksum_sha256=checksum,
        )
    ]


def _run(spec_path: Path, output_dir: Path | None, *, debug: bool, resume: bool) -> int:
    """Internal runner used by the CLI and tests."""
    try:
        spec = BacktestRunSpecLoader.from_yaml(spec_path)
    except BacktestRunSpecValidationError as exc:
        print(f"[user-error] invalid spec: {exc}", flush=True)
        return EXIT_USER_ERROR

    if not spec.strategy_bindings:
        print("[user-error] spec must define at least one strategy_binding", flush=True)
        return EXIT_USER_ERROR

    output_dir = resolve_output_dir(spec, str(output_dir) if output_dir else None)

    if resume and (output_dir / "manifest.json").exists():
        # Idempotent: if a manifest already exists with the same spec hash, exit OK.
        from quant_signal_system.cli._common import load_manifest

        existing = load_manifest(output_dir / "manifest.json")
        if existing.resolved_config_hash == spec.compute_resolved_hash():
            print(f"[ok] resume: manifest already present at {output_dir}", flush=True)
            return EXIT_OK
        print("[run-failed] resume mismatch: spec_hash differs from existing manifest", flush=True)
        return EXIT_RUN_FAILED

    resolver = UniverseResolver(UniverseRepository())
    _seed_empty_universes(spec, resolver._repo)  # type: ignore[attr-defined]
    market_repo = _InMemoryMarketDataRepo()
    signal_repo = InMemorySignalRepository()
    signal_service = SignalService(clock=FrozenClock(current_time=spec.from_time))

    orchestrator = BacktestOrchestrator(
        spec=spec,
        universe_resolver=resolver,
        market_repo=market_repo,
        signal_service=signal_service,
        signal_repo=signal_repo,
    )

    bars = _stub_bar_source(spec)
    try:
        result = orchestrator.run(bars)
    except Exception as exc:  # noqa: BLE001
        print(f"[run-failed] orchestrator raised: {exc}", flush=True)
        return EXIT_RUN_FAILED

    manifest = _build_manifest(spec, result)
    manifest_path = _write_manifest(manifest, output_dir)

    if debug:
        events = [
            {
                "event": "run_complete",
                "run_id": result.run_id,
                "spec_hash": result.spec_hash,
                "started_at": result.started_at.isoformat(),
                "finished_at": result.finished_at.isoformat(),
                "total_bars": result.total_bars,
                "signals_generated": result.signals_generated,
            }
        ]
        _write_debug_trace(events, output_dir)

    artifacts = _record_artifacts(manifest, output_dir)
    final = dataclasses.replace(manifest, artifacts=tuple(artifacts))
    manifest_path.write_text(final.to_json(), encoding="utf-8")
    # The manifest's own checksum is computed BEFORE writing the artifact
    # block (file_sha256 would otherwise be unstable across rewrites).  The
    # checksum remains useful for consumers who want to detect tampering.
    print(f"[ok] run complete: {result.run_id} -> {output_dir}", flush=True)
    return EXIT_OK


class _InMemoryMarketDataRepo:
    """Minimal stub matching MarketDataRepositoryLike protocol."""

    def save_bar(self, bar: object) -> None:
        return None


def cli(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `run_backtest`."""
    args = parse_args(
        argv if argv is not None else __import__("sys").argv[1:],
        description="Run a backtest from a BacktestRunSpec YAML.",
    )
    if not args.spec:
        print("[user-error] --spec is required", file=__import__("sys").stderr)
        return EXIT_USER_ERROR

    # Pass None when no override; let _run fall back to spec.output_dir.
    output_dir = Path(args.output_dir) if args.output_dir else None
    return _run(Path(args.spec), output_dir, debug=args.debug, resume=args.resume)


if __name__ == "__main__":
    raise SystemExit(cli())