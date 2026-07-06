"""Validate backtest manifest command."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from quant_signal_system.cli._common import (
    EXIT_OK,
    EXIT_USER_ERROR,
    EXIT_VALIDATION_FAILED,
    build_artifact_set,
    load_manifest,
    parse_args,
    verify_required_fields,
)
from quant_signal_system.cli._common import file_sha256

REQUIRED_FIELDS = (
    "run_id",
    "run_mode",
    "run_status",
    "created_at",
    "from_time",
    "to_time",
    "data_source_version",
    "as_of_version",
)


def validate(artifact_dir: Path) -> tuple[bool, list[str]]:
    """Validate the manifest under artifact_dir.

    Returns (ok, errors).  ok=True means all checks passed.
    """
    errors: list[str] = []
    manifest_path = artifact_dir / "manifest.json"
    if not manifest_path.exists():
        return False, [f"manifest.json not found in {artifact_dir}"]

    try:
        manifest = load_manifest(manifest_path)
    except Exception as exc:  # noqa: BLE001
        return False, [f"failed to parse manifest.json: {exc}"]

    errors.extend(verify_required_fields(manifest, REQUIRED_FIELDS))

    for name, path, expected in build_artifact_set(manifest, artifact_dir):
        if not path.exists():
            errors.append(f"artifact missing: {name} -> {path}")
            continue
        if expected:
            actual = file_sha256(path)
            if actual != expected:
                errors.append(f"artifact checksum mismatch: {name} (expected {expected[:8]}, got {actual[:8]})")

    return not errors, errors


def cli(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for `validate_backtest`."""
    args = parse_args(
        argv if argv is not None else __import__("sys").argv[1:],
        description="Validate a backtest manifest.",
    )
    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else None
    if artifact_dir is None:
        print("[user-error] --artifact-dir is required", file=__import__("sys").stderr)
        return EXIT_USER_ERROR

    ok, errors = validate(artifact_dir)
    if not ok:
        for err in errors:
            print(f"[validation-failed] {err}", flush=True)
        return EXIT_VALIDATION_FAILED
    print(f"[ok] manifest validated: {artifact_dir}", flush=True)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(cli())