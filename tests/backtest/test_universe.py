"""Tests for universe/ module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.universe import (
    DuplicateUniverseError,
    UniverseNotFoundError,
    UniverseRepository,
    UniverseResolver,
    UniverseSnapshot,
    UniverseUnavailableError,
)


class TestUniverseSnapshot:
    def test_valid_snapshot(self) -> None:
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346", "600519", "000001"),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        snap.validate()
        assert snap.schema_version == "universe-snapshot-v1"
        assert len(snap.symbols) == 3

    def test_empty_symbols_raises(self) -> None:
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=(),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        with pytest.raises(MarketDataValidationError, match="symbols must not be empty"):
            snap.validate()

    def test_available_at_after_effective_raises(self) -> None:
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 6, 15, tzinfo=timezone.utc),
            available_at=datetime(2025, 7, 1, tzinfo=timezone.utc),  # after effective
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        with pytest.raises(MarketDataValidationError, match="available_at must not be after"):
            snap.validate()

    def test_is_visible_at(self) -> None:
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        # before available_at
        assert snap.is_visible_at(datetime(2025, 6, 1, tzinfo=timezone.utc)) is False
        # at available_at
        assert snap.is_visible_at(datetime(2025, 6, 15, tzinfo=timezone.utc)) is True
        # after available_at
        assert snap.is_visible_at(datetime(2025, 7, 2, tzinfo=timezone.utc)) is True

    def test_universe_hash_deterministic(self) -> None:
        params = dict(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346", "600519"),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        h1 = UniverseSnapshot(**params).universe_hash()
        h2 = UniverseSnapshot(**params).universe_hash()
        assert h1 == h2
        assert len(h1) == 16


class TestUniverseRepository:
    def test_save_and_get(self) -> None:
        repo = UniverseRepository()
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        repo.save(snap)
        retrieved = repo.get("hs300", "v20250701")
        assert retrieved.universe_id == "hs300"
        assert retrieved.symbols == ("300346",)

    def test_idempotent_save(self) -> None:
        repo = UniverseRepository()
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        repo.save(snap)
        repo.save(snap)  # idempotent, no raise

    def test_conflict_raises(self) -> None:
        repo = UniverseRepository()
        snap1 = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev001",
            as_of_version="asof-v1",
        )
        repo.save(snap1)
        snap2 = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v20250701",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("600519",),  # different content
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="idx-20250701",
            revision_id="rev002",
            as_of_version="asof-v1",
        )
        with pytest.raises(DuplicateUniverseError):
            repo.save(snap2)

    def test_latest_visible(self) -> None:
        repo = UniverseRepository()
        snap1 = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v1",
            effective_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 12, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="v1",
            revision_id="r1",
            as_of_version="asof-v1",
        )
        snap2 = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v2",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346", "600519"),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="v2",
            revision_id="r2",
            as_of_version="asof-v1",
        )
        repo.save(snap1)
        repo.save(snap2)

        # Before snap2 available
        result = repo.latest_visible("hs300", datetime(2025, 6, 1, tzinfo=timezone.utc))
        assert result is not None
        assert result.universe_version == "v1"

        # After snap2 available
        result = repo.latest_visible("hs300", datetime(2025, 7, 2, tzinfo=timezone.utc))
        assert result is not None
        assert result.universe_version == "v2"

        # No snapshot visible
        result = repo.latest_visible("hs300", datetime(2024, 11, 1, tzinfo=timezone.utc))
        assert result is None

    def test_not_found(self) -> None:
        repo = UniverseRepository()
        with pytest.raises(UniverseNotFoundError):
            repo.get("nonexistent", "v1")


class TestUniverseResolver:
    def test_resolve_visible(self) -> None:
        repo = UniverseRepository()
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v1",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="v1",
            revision_id="r1",
            as_of_version="asof-v1",
        )
        repo.save(snap)
        resolver = UniverseResolver(repo)
        result = resolver.resolve("hs300", datetime(2025, 7, 2, tzinfo=timezone.utc))
        assert result.universe_id == "hs300"

    def test_resolve_not_visible_strict(self) -> None:
        repo = UniverseRepository()
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v1",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346",),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="v1",
            revision_id="r1",
            as_of_version="asof-v1",
        )
        repo.save(snap)
        resolver = UniverseResolver(repo)
        # Query before available_at
        with pytest.raises(UniverseUnavailableError):
            resolver.resolve("hs300", datetime(2025, 6, 1, tzinfo=timezone.utc))

    def test_symbols_for(self) -> None:
        repo = UniverseRepository()
        snap = UniverseSnapshot(
            universe_id="hs300",
            universe_version="v1",
            effective_time=datetime(2025, 7, 1, tzinfo=timezone.utc),
            available_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
            symbols=("300346", "600519", "000001"),
            inclusion_reason="index_constituent",
            source="CSI",
            source_version="v1",
            revision_id="r1",
            as_of_version="asof-v1",
        )
        repo.save(snap)
        resolver = UniverseResolver(repo)
        symbols = resolver.symbols_for("hs300", datetime(2025, 7, 2, tzinfo=timezone.utc))
        assert len(symbols) == 3
