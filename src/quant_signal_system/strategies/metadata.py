"""Static metadata describing a strategy registration.

`StrategySpec` is the immutable description of a strategy as the rest of the
system sees it. The runtime instance carries the same data plus the effective
parameter snapshot, but the spec is what the registry stores, the registry
hands back to callers, and the version registry hashes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from quant_signal_system.contracts.market import MarketDataValidationError


@dataclass(frozen=True, slots=True)
class StrategySpec:
    """Static description of a registered strategy."""

    name: str
    version: str
    code_version: str
    parameter_hash: str
    horizon_seconds: int
    yaml_path: Path | None

    def validate(self) -> None:
        if not self.name or not self.name.strip():
            raise MarketDataValidationError("strategy name is required")
        if not self.version or not self.version.strip():
            raise MarketDataValidationError("strategy version is required")
        if not self.code_version or not self.code_version.strip():
            raise MarketDataValidationError("strategy code_version is required")
        if not self.parameter_hash or not self.parameter_hash.strip():
            raise MarketDataValidationError("strategy parameter_hash is required")
        if self.horizon_seconds <= 0:
            raise MarketDataValidationError("strategy horizon_seconds must be positive")

    @property
    def identity_key(self) -> tuple[str, str, str, str]:
        """Composite identity used for freeze and conflict detection."""

        return (self.name, self.version, self.code_version, self.parameter_hash)

    def describe(self) -> Mapping[str, str]:
        return {
            "strategy_name": self.name,
            "strategy_version": self.version,
            "code_version": self.code_version,
            "parameter_hash": self.parameter_hash,
            "horizon_seconds": str(self.horizon_seconds),
            "yaml_path": "" if self.yaml_path is None else str(self.yaml_path),
        }