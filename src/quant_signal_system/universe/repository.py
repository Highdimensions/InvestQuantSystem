"""Versioned repository for UniverseSnapshot objects."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator

from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.universe.contracts import UniverseSnapshot


class DuplicateUniverseError(MarketDataValidationError):
    """Raised when inserting a UniverseSnapshot with a conflicting identity."""


class UniverseNotFoundError(MarketDataValidationError):
    """Raised when a requested universe_id is not found."""


@dataclass
class UniverseRepository:
    """In-memory, append-only repository for UniverseSnapshot objects.

    Callers can store multiple versions of the same universe_id; queries return
    the latest visible snapshot for a given universe_id and decision_time.
    """

    _snapshots: dict[str, UniverseSnapshot] = field(default_factory=dict)
    _by_id_and_version: dict[tuple[str, str], UniverseSnapshot] = field(default_factory=dict)

    def save(self, snapshot: UniverseSnapshot) -> None:
        """Store a UniverseSnapshot.

        Raises DuplicateUniverseError if the same (universe_id, universe_version)
        is already stored with different content.
        """
        snapshot.validate()
        key = (snapshot.universe_id, snapshot.universe_version)

        existing = self._by_id_and_version.get(key)
        if existing is not None:
            if existing.universe_hash() != snapshot.universe_hash():
                raise DuplicateUniverseError(
                    f"universe {snapshot.universe_id!r} version {snapshot.universe_version!r} "
                    "already stored with different content"
                )
            return  # Idempotent: same content

        self._snapshots[key[0] + "/" + key[1]] = snapshot
        self._by_id_and_version[key] = snapshot

    def get(
        self,
        universe_id: str,
        universe_version: str,
    ) -> UniverseSnapshot:
        """Fetch a specific version of a universe by identity."""
        key = (universe_id, universe_version)
        snapshot = self._by_id_and_version.get(key)
        if snapshot is None:
            raise UniverseNotFoundError(
                f"universe {universe_id!r} version {universe_version!r} not found"
            )
        return snapshot

    def latest_visible(
        self,
        universe_id: str,
        at_time: datetime,
    ) -> UniverseSnapshot | None:
        """Return the latest visible snapshot for universe_id at at_time.

        Returns None if no visible snapshot exists.
        """
        candidates = [
            s for (uid, _), s in self._by_id_and_version.items()
            if uid == universe_id and s.is_visible_at(at_time)
        ]
        if not candidates:
            return None
        # Pick the one with latest effective_time
        return max(candidates, key=lambda s: s.effective_time)

    def get_by_id(self, universe_id: str) -> list[UniverseSnapshot]:
        """Return all versions of a universe_id, sorted by effective_time ascending."""
        result = [
            s for (uid, _), s in self._by_id_and_version.items()
            if uid == universe_id
        ]
        result.sort(key=lambda s: s.effective_time)
        return result

    def all_snapshots(self) -> Iterator[UniverseSnapshot]:
        """Iterate over all stored snapshots."""
        seen: set[str] = set()
        for snapshot in self._snapshots.values():
            key = snapshot.universe_hash()
            if key not in seen:
                seen.add(key)
                yield snapshot


def universe_id_from_index(series: str) -> str:
    """Derive a universe_id from an index name.

    Examples:
        HS300 -> "hs300"
        CSI 500 -> "csi500"
    """
    cleaned = series.strip().lower().replace(" ", "_")
    return hashlib.md5(cleaned.encode("utf-8")).hexdigest()[:8] + "_" + cleaned
