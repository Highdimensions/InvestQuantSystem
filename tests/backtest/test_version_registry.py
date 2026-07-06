"""Tests for config/versions.py thread-safety fix."""

from __future__ import annotations

import threading

import pytest

from quant_signal_system.config.versions import (
    DuplicateStrategyFreezeError,
    VersionRegistry,
)


class TestVersionRegistryThreadSafety:
    def test_freeze_strategy_idempotent(self) -> None:
        registry = VersionRegistry()
        sv1 = registry.freeze_strategy(
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="abc",
            code_version="c1",
        )
        sv2 = registry.freeze_strategy(
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="abc",
            code_version="c1",
        )
        # Should return the same frozen identity (idempotent)
        assert sv1.strategy_name == sv2.strategy_name
        assert sv1.created_at == sv2.created_at

    def test_freeze_strategy_conflict_raises(self) -> None:
        registry = VersionRegistry()
        registry.freeze_strategy(
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="abc",
            code_version="c1",
        )
        with pytest.raises(DuplicateStrategyFreezeError):
            registry.freeze_strategy(
                strategy_name="x",
                strategy_version="v1",
                parameter_hash="def",  # different hash
                code_version="c1",
            )

    def test_is_strategy_frozen(self) -> None:
        registry = VersionRegistry()
        registry.freeze_strategy(
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="abc",
            code_version="c1",
        )
        assert registry.is_strategy_frozen(
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="abc",
            code_version="c1",
        )
        assert not registry.is_strategy_frozen(
            strategy_name="x",
            strategy_version="v1",
            parameter_hash="def",
            code_version="c1",
        )

    def test_concurrent_freeze_is_idempotent(self) -> None:
        """Multiple threads freezing the same identity simultaneously must not raise."""
        registry = VersionRegistry()
        errors: list[Exception] = []
        successes: list[str] = []
        lock = threading.Lock()

        def freeze_same() -> None:
            try:
                for _ in range(100):
                    sv = registry.freeze_strategy(
                        strategy_name="concurrent_test",
                        strategy_version="v1",
                        parameter_hash="abc123",
                        code_version="c1",
                    )
                    with lock:
                        successes.append(sv.strategy_name)
            except DuplicateStrategyFreezeError:
                pass  # fine: conflict between different identity
            except Exception as exc:  # pragma: no cover
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=freeze_same) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(successes) == 1000  # 10 threads × 100 each

    def test_concurrent_freeze_different_identities_no_conflict(self) -> None:
        """Different strategy identities should never conflict even with concurrency."""
        registry = VersionRegistry()
        errors: list[Exception] = []

        def freeze_variants(base: int) -> None:
            try:
                for i in range(50):
                    registry.freeze_strategy(
                        strategy_name=f"strat_{base}_{i}",
                        strategy_version="v1",
                        parameter_hash=f"hash_{base}_{i}",
                        code_version="c1",
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=freeze_variants, args=(b,)) for b in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors

    def test_frozen_strategies_returns_all(self) -> None:
        registry = VersionRegistry()
        for i in range(5):
            registry.freeze_strategy(
                strategy_name=f"s{i}",
                strategy_version="v1",
                parameter_hash=f"h{i}",
                code_version="c1",
            )
        frozen = registry.frozen_strategies()
        assert len(frozen) == 5

    def test_frozen_strategies_immutable_view(self) -> None:
        registry = VersionRegistry()
        registry.freeze_strategy(
            strategy_name="s1",
            strategy_version="v1",
            parameter_hash="h1",
            code_version="c1",
        )
        frozen1 = registry.frozen_strategies()
        # Register another one
        registry.freeze_strategy(
            strategy_name="s2",
            strategy_version="v1",
            parameter_hash="h2",
            code_version="c1",
        )
        frozen2 = registry.frozen_strategies()
        assert len(frozen1) == 1  # old view unchanged
        assert len(frozen2) == 2
