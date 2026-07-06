"""Universe resolver that returns the visible snapshot for a given time and universe_id."""

from __future__ import annotations

from datetime import datetime

from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.universe.contracts import UniverseSnapshot
from quant_signal_system.universe.repository import UniverseNotFoundError, UniverseRepository


class UniverseUnavailableError(MarketDataValidationError):
    """Raised when a universe snapshot is not visible at the required time."""


class UniverseResolver:
    """Resolves UniverseSnapshot instances given a universe_id and decision time.

    The resolver ensures that as-of semantics are respected: a snapshot is only
    returned if its available_at is at or before the decision time.
    """

    def __init__(self, repository: UniverseRepository) -> None:
        self._repo = repository

    def resolve(
        self,
        universe_id: str,
        at_time: datetime,
        require_strict: bool = True,
    ) -> UniverseSnapshot:
        """Resolve the latest visible UniverseSnapshot for universe_id at at_time.

        Args:
            universe_id: The universe identifier.
            at_time: The decision time used for as-of filtering.
            require_strict: If True (default), raises UniverseUnavailableError when
                no visible snapshot exists. If False, returns the latest effective
                snapshot even if not yet visible (for diagnostics only).

        Returns:
            The latest visible UniverseSnapshot.

        Raises:
            UniverseUnavailableError: No visible snapshot exists and require_strict=True.
        """
        snapshot = self._repo.latest_visible(universe_id, at_time)
        if snapshot is not None:
            return snapshot

        if require_strict:
            raise UniverseUnavailableError(
                f"no visible universe {universe_id!r} at {at_time}"
            )

        # Diagnostics: return latest effective even if not yet visible
        all_versions = self._repo.get_by_id(universe_id)
        if all_versions:
            return all_versions[-1]

        raise UniverseNotFoundError(f"universe {universe_id!r} not found")

    def symbols_for(
        self,
        universe_id: str,
        at_time: datetime,
    ) -> tuple[str, ...]:
        """Convenience: return the symbol tuple for a universe at a given time."""
        snapshot = self.resolve(universe_id, at_time)
        return snapshot.symbols
