"""Backtest run specification and strategy binding contracts."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from quant_signal_system.config.data_source import DataSourceProfile
from quant_signal_system.contracts.market import MarketDataValidationError, require_aware_utc
from quant_signal_system.universe.contracts import UniverseSnapshot


# ---------------------------------------------------------------------------
# StrategyBinding
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StrategyBinding:
    """Binds a strategy to a universe, parameter set, and versioned dependencies.

    The same strategy name may have multiple active bindings with different
    parameter sets (different binding_ids).  Bindings MUST NOT be shared across
    different universes to prevent silent re-use of stale constituents.
    """

    # Identity (required)
    binding_id: str
    strategy_name: str
    strategy_version: str
    parameter_hash: str

    # Binding relationships (required)
    universe_id: str
    universe_version: str

    # Versioned dependencies (required)
    feature_version: str

    # Optional / with defaults
    schema_version: str = "strategy-binding-v1"
    composer_policy: str = "PRIORITY_MAX_CONFIDENCE"
    market_rule_version: str | None = None
    cost_model_version: str = "fixed-bps-v1"
    fill_model_version: str = "next-bar-open-v1"
    weight: Decimal = field(default_factory=lambda: Decimal("1.0"))
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    description: str = ""
    yaml_path: Path | None = None

    def validate(self) -> None:
        """Validate identity fields and temporal constraints."""
        if not self.binding_id or not self.binding_id.strip():
            raise MarketDataValidationError("binding_id is required")
        if not self.strategy_name or not self.strategy_name.strip():
            raise MarketDataValidationError("strategy_name is required")
        if not self.strategy_version or not self.strategy_version.strip():
            raise MarketDataValidationError("strategy_version is required")
        if not self.parameter_hash or not self.parameter_hash.strip():
            raise MarketDataValidationError("parameter_hash is required")
        if not self.universe_id or not self.universe_id.strip():
            raise MarketDataValidationError("universe_id is required")
        if not self.universe_version or not self.universe_version.strip():
            raise MarketDataValidationError("universe_version is required")
        if not self.feature_version or not self.feature_version.strip():
            raise MarketDataValidationError("feature_version is required")
        if self.weight < 0:
            raise MarketDataValidationError("weight must be non-negative")
        if self.valid_from is not None:
            require_aware_utc(self.valid_from, "valid_from")
        if self.valid_to is not None:
            require_aware_utc(self.valid_to, "valid_to")
        if self.valid_from is not None and self.valid_to is not None:
            if self.valid_from >= self.valid_to:
                raise MarketDataValidationError("valid_from must be before valid_to")


# ---------------------------------------------------------------------------
# BacktestRunSpec
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BacktestRunSpec:
    """Describes a complete, reproducible backtest run.

    A BacktestRunSpec is immutable once created.  To modify a spec callers
    must create a new instance via ``BacktestRunSpecLoader`` or ``.replace(...)``.
    """

    schema_version: str = "backtest-run-spec-v1"

    # Run identity (generated on creation)
    run_id: str = ""
    run_mode: str = "backtest"  # "backtest" | "replay" | "shadow"

    # Time range
    from_time: datetime = field(default_factory=lambda: datetime(2000, 1, 1, tzinfo=timezone.utc))
    to_time: datetime = field(default_factory=lambda: datetime(2100, 1, 1, tzinfo=timezone.utc))
    timeframe: str = "1m"

    # Data source
    data_source_profile: DataSourceProfile | None = None
    data_source_version: str = ""
    as_of_version: str = ""
    market_data_paths: tuple[str, ...] = field(default_factory=tuple)

    # Strategy bindings (at least one required)
    strategy_bindings: tuple[StrategyBinding, ...] = field(default_factory=tuple)

    # Market and execution
    market_rule_version: str | None = None
    cost_model_version: str = "fixed-bps-v1"
    fill_model_version: str = "next-bar-open-v1"
    initial_cash: Decimal = field(default_factory=lambda: Decimal("1000000"))

    # Determinism
    clock_policy: str = "frozen"
    random_seed: int | None = None

    # Output
    output_dir: Path = field(default_factory=lambda: Path("artifacts/backtests"))

    # Environment (populated at resolve time)
    git_commit: str = ""
    git_branch: str = ""
    python_version: str = field(default_factory=lambda: ".".join(map(str, sys.version_info[:3])))
    platform: str = field(default_factory=lambda: sys.platform)

    # Resolved (populated by resolve())
    resolved_config_hash: str | None = None
    universe_snapshots: tuple[UniverseSnapshot, ...] = field(default_factory=tuple)

    def _post_init_validation(self) -> None:
        require_aware_utc(self.from_time, "from_time")
        require_aware_utc(self.to_time, "to_time")
        if self.from_time >= self.to_time:
            raise MarketDataValidationError("from_time must be before to_time")
        if self.timeframe not in ("1m", "5m", "15m", "1h", "1d"):
            raise MarketDataValidationError(f"unknown timeframe: {self.timeframe!r}")
        if not self.strategy_bindings:
            raise MarketDataValidationError("at least one strategy_binding is required")

    def __post_init__(self) -> None:
        self._post_init_validation()

    def compute_resolved_hash(self) -> str:
        """Compute a deterministic hash of the resolved configuration.

        The hash covers all versioned fields that affect backtest reproducibility.
        """
        parts: dict[str, Any] = {
            "run_mode": self.run_mode,
            "from_time": self.from_time.isoformat(),
            "to_time": self.to_time.isoformat(),
            "timeframe": self.timeframe,
            "data_source_version": self.data_source_version,
            "as_of_version": self.as_of_version,
            "market_rule_version": self.market_rule_version,
            "cost_model_version": self.cost_model_version,
            "fill_model_version": self.fill_model_version,
            "clock_policy": self.clock_policy,
            "random_seed": self.random_seed,
            "initial_cash": str(self.initial_cash),
            "bindings": [],
        }
        for b in self.strategy_bindings:
            parts["bindings"].append(
                {
                    "binding_id": b.binding_id,
                    "strategy_name": b.strategy_name,
                    "strategy_version": b.strategy_version,
                    "parameter_hash": b.parameter_hash,
                    "universe_id": b.universe_id,
                    "universe_version": b.universe_version,
                    "feature_version": b.feature_version,
                    "composer_policy": b.composer_policy,
                    "weight": str(b.weight),
                    "valid_from": b.valid_from.isoformat() if b.valid_from else None,
                    "valid_to": b.valid_to.isoformat() if b.valid_to else None,
                }
            )
        encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


# ---------------------------------------------------------------------------
# BacktestRunSpecLoader
# ---------------------------------------------------------------------------


class BacktestRunSpecValidationError(MarketDataValidationError):
    """Raised when a run spec YAML/JSON fails validation."""


class BacktestRunSpecLoader:
    """Loads and validates a BacktestRunSpec from YAML or JSON."""

    @classmethod
    def from_yaml(cls, path: str | Path) -> BacktestRunSpec:
        """Load a BacktestRunSpec from a YAML file."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise BacktestRunSpecValidationError(f"cannot read spec file {path}: {exc}") from exc

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise BacktestRunSpecValidationError(f"invalid YAML in {path}: {exc}") from exc

        return cls._from_dict(data, source=str(path))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacktestRunSpec:
        """Load a BacktestRunSpec from a dict (JSON-decoded)."""
        return cls._from_dict(data, source="dict")

    @classmethod
    def _from_dict(cls, data: dict[str, Any], source: str) -> BacktestRunSpec:
        errors: list[str] = []
        try:
            bindings: list[StrategyBinding] = []
            for bdata in data.get("strategy_bindings", []):
                try:
                    binding = cls._parse_binding(bdata)
                    binding.validate()
                    bindings.append(binding)
                except Exception as exc:
                    errors.append(f"binding {bdata.get('binding_id', '?')}: {exc}")

            if errors:
                raise BacktestRunSpecValidationError(
                    f"spec validation errors in {source}:\n  " + "\n  ".join(errors)
                )

            spec = BacktestRunSpec(
                run_id=data.get("run_id", ""),
                run_mode=data.get("run_mode", "backtest"),
                from_time=cls._parse_datetime(data.get("from_time")),
                to_time=cls._parse_datetime(data.get("to_time")),
                timeframe=data.get("timeframe", "1m"),
                data_source_version=data.get("data_source_version", ""),
                as_of_version=data.get("as_of_version", ""),
                market_data_paths=tuple(data.get("market_data_paths", [])),
                strategy_bindings=tuple(bindings),
                market_rule_version=data.get("market_rule_version"),
                cost_model_version=data.get("cost_model_version", "fixed-bps-v1"),
                fill_model_version=data.get("fill_model_version", "next-bar-open-v1"),
                initial_cash=Decimal(str(data.get("initial_cash", "1000000"))),
                clock_policy=data.get("clock_policy", "frozen"),
                random_seed=data.get("random_seed"),
                output_dir=Path(data.get("output_dir", "artifacts/backtests")),
            )
            return spec
        except BacktestRunSpecValidationError:
            raise
        except Exception as exc:
            raise BacktestRunSpecValidationError(
                f"failed to parse spec from {source}: {exc}"
            ) from exc

    @classmethod
    def _parse_binding(cls, bdata: dict[str, Any]) -> StrategyBinding:
        return StrategyBinding(
            binding_id=bdata["binding_id"],
            strategy_name=bdata["strategy_name"],
            strategy_version=bdata["strategy_version"],
            parameter_hash=bdata["parameter_hash"],
            universe_id=bdata["universe_id"],
            universe_version=bdata["universe_version"],
            feature_version=bdata.get("feature_version", "rolling-feature-v1"),
            composer_policy=bdata.get("composer_policy", "PRIORITY_MAX_CONFIDENCE"),
            market_rule_version=bdata.get("market_rule_version"),
            cost_model_version=bdata.get("cost_model_version", "fixed-bps-v1"),
            fill_model_version=bdata.get("fill_model_version", "next-bar-open-v1"),
            weight=Decimal(str(bdata.get("weight", "1.0"))),
            valid_from=cls._parse_datetime(bdata.get("valid_from")),
            valid_to=cls._parse_datetime(bdata.get("valid_to")),
            description=bdata.get("description", ""),
        )

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Accept ISO format strings
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                for tz_suffix, tz in (("Z", timezone.utc), ("", None)):
                    s = value.replace(tz_suffix, "")
                    try:
                        dt = datetime.strptime(s, fmt)
                        if tz is not None:
                            dt = dt.replace(tzinfo=tz)
                        elif dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except ValueError:
                        pass
            raise BacktestRunSpecValidationError(f"unrecognised datetime format: {value!r}")
        raise BacktestRunSpecValidationError(f"expected datetime, got {type(value).__name__!r}")
