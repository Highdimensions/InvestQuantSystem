"""Deterministic config snapshot and strategy freeze registry.

Two related capabilities live here:

* `VersionRegistry.freeze(versions)` produces a content-addressed
  `ConfigSnapshot` for arbitrary version dictionaries (existing behaviour).
* `VersionRegistry.freeze_strategy(...)` registers the four-tuple
  ``(strategy_name, strategy_version, parameter_hash, code_version)`` as a
  frozen strategy identity. Once frozen, `SignalService` can verify that any
  incoming `SignalCandidate` carries an identity the rest of the system has
  acknowledged.
* `VersionRegistry.frozen_strategies()` exposes the snapshot of frozen
  identities so tests and dashboards can audit what is currently allowed.

Frozen strategies are an append-only in-memory table. Callers cannot silently
mutate a frozen identity: registering a different combination of the four
fields under the same name is treated as a new registration rather than an
update.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.contracts.versions import ConfigSnapshot, StrategyStatus, StrategyVersion


class DuplicateStrategyFreezeError(MarketDataValidationError):
    """Raised when re-freezing a strategy with conflicting identity fields."""


@dataclass(slots=True)
class _FrozenStrategy:
    name: str
    strategy_version: str
    parameter_hash: str
    code_version: str
    frozen_at: datetime


class VersionRegistry:
    def __init__(self) -> None:
        self._frozen_strategies: dict[str, _FrozenStrategy] = {}

    def freeze(self, versions: Mapping[str, str]) -> ConfigSnapshot:
        encoded = json.dumps(dict(sorted(versions.items())), separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        return ConfigSnapshot(
            snapshot_id=digest[:16],
            created_at=datetime.now(timezone.utc),
            versions=dict(versions),
            parameter_hash=digest,
        )

    def freeze_strategy(
        self,
        *,
        strategy_name: str,
        strategy_version: str,
        parameter_hash: str,
        code_version: str,
    ) -> StrategyVersion:
        """Register a four-tuple identity as the authoritative frozen strategy.

        Re-freezing the same identity is idempotent and returns the existing
        `StrategyVersion`. Re-freezing the same name with a different
        ``(strategy_version, parameter_hash, code_version)`` is rejected with
        `DuplicateStrategyFreezeError`.
        """

        if not strategy_name or not strategy_name.strip():
            raise MarketDataValidationError("strategy_name is required")
        if not strategy_version or not strategy_version.strip():
            raise MarketDataValidationError("strategy_version is required")
        if not parameter_hash or not parameter_hash.strip():
            raise MarketDataValidationError("parameter_hash is required")
        if not code_version or not code_version.strip():
            raise MarketDataValidationError("code_version is required")

        existing = self._frozen_strategies.get(strategy_name)
        if existing is not None:
            if (
                existing.strategy_version == strategy_version
                and existing.parameter_hash == parameter_hash
                and existing.code_version == code_version
            ):
                return StrategyVersion(
                    strategy_name=strategy_name,
                    strategy_version=strategy_version,
                    feature_version="unknown",
                    parameter_hash=parameter_hash,
                    code_version=code_version,
                    created_at=existing.frozen_at,
                    description="frozen",
                    status=StrategyStatus.ACTIVE_RESEARCH,
                )
            raise DuplicateStrategyFreezeError(
                f"strategy {strategy_name!r} already frozen with a different identity"
            )

        now = datetime.now(timezone.utc)
        self._frozen_strategies[strategy_name] = _FrozenStrategy(
            name=strategy_name,
            strategy_version=strategy_version,
            parameter_hash=parameter_hash,
            code_version=code_version,
            frozen_at=now,
        )
        return StrategyVersion(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            feature_version="unknown",
            parameter_hash=parameter_hash,
            code_version=code_version,
            created_at=now,
            description="frozen",
            status=StrategyStatus.ACTIVE_RESEARCH,
        )

    def is_strategy_frozen(
        self,
        *,
        strategy_name: str,
        strategy_version: str,
        parameter_hash: str,
        code_version: str,
    ) -> bool:
        existing = self._frozen_strategies.get(strategy_name)
        if existing is None:
            return False
        return (
            existing.strategy_version == strategy_version
            and existing.parameter_hash == parameter_hash
            and existing.code_version == code_version
        )

    def frozen_strategies(self) -> tuple[StrategyVersion, ...]:
        return tuple(
            StrategyVersion(
                strategy_name=item.name,
                strategy_version=item.strategy_version,
                feature_version="unknown",
                parameter_hash=item.parameter_hash,
                code_version=item.code_version,
                created_at=item.frozen_at,
                description="frozen",
                status=StrategyStatus.ACTIVE_RESEARCH,
            )
            for item in self._frozen_strategies.values()
        )