"""Shared helpers for CLI commands."""

from __future__ import annotations

import json
import sys
from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from quant_signal_system.backtest.manifest import BacktestRunManifest
from quant_signal_system.backtest.run_spec import BacktestRunSpec

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_RUN_FAILED = 2
EXIT_VALIDATION_FAILED = 3


def parse_args(argv: Sequence[str], *, description: str) -> Namespace:
    """Parse common CLI arguments."""
    parser = ArgumentParser(description=description)
    parser.add_argument("--spec", type=str, help="Path to BacktestRunSpec YAML")
    parser.add_argument("--output-dir", type=str, help="Override output directory")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--resume", action="store_true", help="Resume from previous run")
    parser.add_argument("--run-id", type=str, help="Run identifier")
    parser.add_argument("--run-id-a", type=str, help="First run id for comparison")
    parser.add_argument("--run-id-b", type=str, help="Second run id for comparison")
    parser.add_argument("--artifact-dir", type=str, help="Directory containing artifacts")
    return parser.parse_args(list(argv))


def resolve_output_dir(spec: BacktestRunSpec, override: str | None) -> Path:
    """Resolve the output directory, applying an override if provided."""
    if override:
        return Path(override)
    return spec.output_dir


def exit_with(code: int, message: str | None = None) -> None:
    """Print message to stderr if given and exit with the given code."""
    if message:
        print(message, file=sys.stderr)
    sys.exit(code)


def load_manifest(path: Path) -> BacktestRunManifest:
    """Load a manifest from JSON."""
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return BacktestRunManifest.from_dict(data)


def utc_now() -> datetime:
    """Return current UTC time."""
    return datetime.now(timezone.utc)


def file_sha256(path: Path) -> str:
    """Compute SHA256 of a file."""
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def build_artifact_set(manifest: BacktestRunManifest, artifact_dir: Path) -> list[tuple[str, Path, str]]:
    """Build (name, path, expected_sha256) triples for verification."""
    items: list[tuple[str, Path, str]] = []
    for ref in manifest.artifacts:
        if not ref.artifact_path:
            continue
        # Skip the manifest's own self-reference: including it in checksum
        # verification would make the file structurally self-referential and
        # unstable across re-writes.
        if ref.artifact_name == "manifest":
            continue
        items.append((ref.artifact_name, artifact_dir / ref.artifact_path, ref.checksum_sha256))
    return items


def verify_required_fields(manifest: BacktestRunManifest, fields: Sequence[str]) -> list[str]:
    """Return list of missing-field errors."""
    errors: list[str] = []
    for field in fields:
        value = getattr(manifest, field, None)
        if value is None or value == "" or value == ():
            errors.append(f"missing required field: {field}")
    return errors


def diff_dicts(left: Mapping[str, object], right: Mapping[str, object]) -> dict[str, tuple[object, object]]:
    """Return keys where left and right differ (excluding equal values)."""
    diff: dict[str, tuple[object, object]] = {}
    keys = set(left) | set(right)
    for key in keys:
        lv = left.get(key)
        rv = right.get(key)
        if lv != rv:
            diff[key] = (lv, rv)
    return diff