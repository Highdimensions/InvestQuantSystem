"""Backtest run manifest: metadata, versions, warnings, and artifact registry."""

from __future__ import annotations

import dataclasses
import json
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from quant_signal_system.contracts.market import MarketDataValidationError


# ---------------------------------------------------------------------------
# Supporting types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunWarning:
    """A warning raised during a backtest run."""

    schema_version: str = "run-warning-v1"
    warning_code: str = ""
    severity: str = ""  # "info" | "warn" | "error"
    message: str = ""
    affected_symbols: tuple[str, ...] = field(default_factory=tuple, kw_only=True)
    affected_time_range: tuple[datetime, datetime] | None = field(default=None, kw_only=True)
    count: int = field(default=1, kw_only=True)


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """Reference to a backtest output artifact."""

    schema_version: str = "artifact-ref-v1"
    artifact_name: str = ""
    artifact_path: str = ""   # relative to output_dir
    artifact_type: str = ""   # "json" | "csv" | "md" | "parquet"
    record_count: int | None = field(default=None, kw_only=True)
    checksum_sha256: str = field(default="", kw_only=True)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc), kw_only=True)


@dataclass(frozen=True, slots=True)
class AssertionResult:
    """Result of a single backtest assertion check."""

    schema_version: str = "assertion-result-v1"
    assertion_name: str = ""
    passed: bool = False
    detail: str = field(default="", kw_only=True)


# ---------------------------------------------------------------------------
# BacktestRunManifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BacktestRunManifest:
    """Complete metadata and artifact registry for a backtest run.

    A manifest is the single source of truth about what was run, what versions
    were used, and where the outputs live.  It MUST be written before the run
    is considered complete.
    """

    # Run identity (required)
    run_id: str
    run_mode: str          # "backtest" | "replay" | "shadow"
    run_status: str        # "success" | "failed" | "partial" | "cancelled"

    # Lifecycle (required)
    created_at: datetime

    # With defaults
    schema_version: str = "backtest-run-manifest-v1"
    completed_at: datetime | None = None
    duration_seconds: float | None = None

    # Config snapshots
    original_spec_yaml: str = ""
    resolved_config_hash: str = ""

    # Environment versions
    git_commit: str = ""
    git_branch: str = ""
    python_version: str = ""
    platform_name: str = ""
    engine_version: str = "backtest-v1"

    # Core versions
    strategy_versions: tuple[str, ...] = field(default_factory=tuple)
    feature_versions: tuple[str, ...] = field(default_factory=tuple)
    universe_versions: tuple[str, ...] = field(default_factory=tuple)
    data_source_version: str = ""
    as_of_version: str = ""
    calendar_version: str = ""
    cost_model_version: str = ""
    fill_model_version: str = ""
    market_rule_version: str = ""

    # Data range
    from_time: datetime = field(default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc))
    to_time: datetime = field(default_factory=lambda: datetime(2100, 1, 1, tzinfo=timezone.utc))
    timeframe: str = "1m"

    # Runtime statistics
    total_bars_processed: int = 0
    total_bars_skipped: int = 0
    total_signals_generated: int = 0
    total_signals_rejected: int = 0
    total_order_intents: int = 0
    total_orders_accepted: int = 0
    total_orders_rejected: int = 0
    total_fills: int = 0
    total_evaluations_completed: int = 0
    total_evaluations_postponed: int = 0
    peak_memory_mb: float | None = None

    # Warnings
    warnings: tuple[RunWarning, ...] = field(default_factory=tuple)

    # Data quality
    missing_bar_count: int = 0
    duplicate_bar_count: int = 0
    out_of_order_bar_count: int = 0
    quarantine_record_count: int = 0

    # Artifacts
    artifacts: tuple[ArtifactRef, ...] = field(default_factory=tuple)

    # Determinism check
    deterministic_check_passed: bool = False
    deterministic_check_detail: str = ""

    # Assertions
    expected_assertions: tuple[str, ...] = field(default_factory=tuple)
    assertion_results: tuple[AssertionResult, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        """Basic structural validation."""
        if not self.run_id:
            raise MarketDataValidationError("run_id is required")
        if self.run_status not in ("success", "failed", "partial", "cancelled"):
            raise MarketDataValidationError(f"unknown run_status: {self.run_status!r}")
        if self.created_at.tzinfo is None:
            raise MarketDataValidationError("created_at must be timezone-aware UTC")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict.

        Uses dataclasses.asdict to handle slots=True dataclasses correctly.
        """
        def _serialize(obj: object) -> object:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, (RunWarning, ArtifactRef, AssertionResult)):
                return dataclasses.asdict(obj)
            if isinstance(obj, (tuple, list)):
                return [_serialize(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _serialize(v) for k, v in obj.items()}
            return obj

        raw = _serialize(dataclasses.asdict(self))
        return raw

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacktestRunManifest:
        """Deserialize from a JSON-compatible dict."""
        def _deserialize(obj: Any) -> Any:
            if isinstance(obj, dict):
                # Detect specific types by schema_version or keys
                if "schema_version" in obj:
                    sv = obj["schema_version"]
                    if "artifact-ref" in sv:
                        return ArtifactRef(**obj)
                    if "assertion-result" in sv:
                        return AssertionResult(**obj)
                    if "run-warning" in sv:
                        return RunWarning(**obj)
                return {k: _deserialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_deserialize(x) for x in obj]
            return obj

        d = _deserialize(data)
        return cls(**d)


# ---------------------------------------------------------------------------
# ManifestBuilder
# ---------------------------------------------------------------------------


class ManifestBuilder:
    """Incremental builder for BacktestRunManifest.

    Usage::

        builder = ManifestBuilder(run_id="run_001", created_at=utcnow())
        builder.set_config_snapshot(original_yaml=..., resolved_hash=...)
        builder.set_versions(strategy_versions=..., ...)
        builder.add_warning(RunWarning(...))
        manifest = builder.build()
    """

    def __init__(
        self,
        run_id: str,
        created_at: datetime | None = None,
    ) -> None:
        if not run_id:
            raise ValueError("run_id is required")
        self._created_at = created_at or datetime.now(timezone.utc)
        self._data: dict[str, Any] = {
            "run_id": run_id,
            "run_mode": "backtest",
            "run_status": "failed",
            "created_at": self._created_at,
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "platform_name": platform.platform(),
            "git_commit": self._get_git_commit(),
            "git_branch": self._get_git_branch(),
        }

    def set_run_mode(self, mode: str) -> ManifestBuilder:
        self._data["run_mode"] = mode
        return self

    def set_config_snapshot(
        self,
        original_spec_yaml: str,
        resolved_config_hash: str,
    ) -> ManifestBuilder:
        self._data["original_spec_yaml"] = original_spec_yaml
        self._data["resolved_config_hash"] = resolved_config_hash
        return self

    def set_versions(
        self,
        *,
        strategy_versions: tuple[str, ...] = (),
        feature_versions: tuple[str, ...] = (),
        universe_versions: tuple[str, ...] = (),
        data_source_version: str = "",
        as_of_version: str = "",
        calendar_version: str = "",
        cost_model_version: str = "",
        fill_model_version: str = "",
        market_rule_version: str = "",
    ) -> ManifestBuilder:
        self._data.update(
            {
                "strategy_versions": strategy_versions,
                "feature_versions": feature_versions,
                "universe_versions": universe_versions,
                "data_source_version": data_source_version,
                "as_of_version": as_of_version,
                "calendar_version": calendar_version,
                "cost_model_version": cost_model_version,
                "fill_model_version": fill_model_version,
                "market_rule_version": market_rule_version,
            }
        )
        return self

    def set_data_range(
        self,
        from_time: datetime,
        to_time: datetime,
        timeframe: str,
    ) -> ManifestBuilder:
        self._data["from_time"] = from_time
        self._data["to_time"] = to_time
        self._data["timeframe"] = timeframe
        return self

    def set_statistics(
        self,
        *,
        total_bars_processed: int = 0,
        total_bars_skipped: int = 0,
        total_signals_generated: int = 0,
        total_signals_rejected: int = 0,
        total_order_intents: int = 0,
        total_orders_accepted: int = 0,
        total_orders_rejected: int = 0,
        total_fills: int = 0,
        total_evaluations_completed: int = 0,
        total_evaluations_postponed: int = 0,
        peak_memory_mb: float | None = None,
    ) -> ManifestBuilder:
        self._data.update(
            {
                "total_bars_processed": total_bars_processed,
                "total_bars_skipped": total_bars_skipped,
                "total_signals_generated": total_signals_generated,
                "total_signals_rejected": total_signals_rejected,
                "total_order_intents": total_order_intents,
                "total_orders_accepted": total_orders_accepted,
                "total_orders_rejected": total_orders_rejected,
                "total_fills": total_fills,
                "total_evaluations_completed": total_evaluations_completed,
                "total_evaluations_postponed": total_evaluations_postponed,
                "peak_memory_mb": peak_memory_mb,
            }
        )
        return self

    def set_data_quality(
        self,
        *,
        missing_bar_count: int = 0,
        duplicate_bar_count: int = 0,
        out_of_order_bar_count: int = 0,
        quarantine_record_count: int = 0,
    ) -> ManifestBuilder:
        self._data.update(
            {
                "missing_bar_count": missing_bar_count,
                "duplicate_bar_count": duplicate_bar_count,
                "out_of_order_bar_count": out_of_order_bar_count,
                "quarantine_record_count": quarantine_record_count,
            }
        )
        return self

    def add_warning(self, warning: RunWarning) -> ManifestBuilder:
        warnings = list(self._data.get("warnings", ()))
        warnings.append(warning)
        self._data["warnings"] = tuple(warnings)
        return self

    def add_artifact(self, artifact: ArtifactRef) -> ManifestBuilder:
        artifacts = list(self._data.get("artifacts", ()))
        artifacts.append(artifact)
        self._data["artifacts"] = tuple(artifacts)
        return self

    def add_assertion(self, result: AssertionResult) -> ManifestBuilder:
        results = list(self._data.get("assertion_results", ()))
        results.append(result)
        self._data["assertion_results"] = tuple(results)
        expected = list(self._data.get("expected_assertions", ()))
        if result.assertion_name not in expected:
            expected.append(result.assertion_name)
        self._data["expected_assertions"] = tuple(expected)
        return self

    def set_deterministic_check(
        self,
        passed: bool,
        detail: str = "",
    ) -> ManifestBuilder:
        self._data["deterministic_check_passed"] = passed
        self._data["deterministic_check_detail"] = detail
        return self

    def finalize(
        self,
        run_status: str,
        completed_at: datetime | None = None,
    ) -> BacktestRunManifest:
        """Build the final manifest and set completion metadata."""
        self._data["run_status"] = run_status
        now = completed_at or datetime.now(timezone.utc)
        self._data["completed_at"] = now
        if self._data.get("created_at"):
            delta = now - self._data["created_at"]
            self._data["duration_seconds"] = round(delta.total_seconds(), 3)
        return BacktestRunManifest(**self._data)

    # -------------------------------------------------------------------------
    # Git helpers (fail silently in CI / no-git environments)
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_git_commit() -> str:
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() or ""
        except Exception:
            return ""

    @staticmethod
    def _get_git_branch() -> str:
        try:
            import subprocess

            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() or ""
        except Exception:
            return ""
