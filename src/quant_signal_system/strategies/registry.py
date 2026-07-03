"""Process-local registry of strategy runtimes.

The registry is the only place where a strategy identity is bound to its
implementation and its parameter payload. Registration is explicit:

1. The caller passes the strategy class (must satisfy `StrategyRuntime`).
2. The caller optionally passes a parameter payload (YAML path, inline JSON
   string, or mapping).
3. The registry resolves parameters against the strategy's declared schema,
   builds a `StrategySpec`, and freezes it through `VersionRegistry`.
4. Subsequent `get(name)` calls materialise an instance with those frozen
   parameters.

The registry is thread-safe and idempotent: registering the same identity
twice is a no-op. Registering a different identity under the same name raises
`DuplicateStrategyError`.
"""

from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from quant_signal_system.config.versions import (
    DuplicateStrategyFreezeError,
    VersionRegistry,
)
from quant_signal_system.contracts.market import MarketDataValidationError
from quant_signal_system.strategies.metadata import StrategySpec
from quant_signal_system.strategies.protocol import StrategyRuntime
from quant_signal_system.strategies.schema import ParamSchema
from quant_signal_system.strategies.yaml_loader import (
    describe_payload,
    load_params,
)


class DuplicateStrategyError(MarketDataValidationError):
    """Raised when re-registering a strategy with a conflicting identity."""


class UnknownStrategyError(MarketDataValidationError):
    """Raised when looking up an unregistered strategy name."""


def _default_version_registry() -> VersionRegistry:
    return VersionRegistry()


@dataclass(slots=True)
class _Registration:
    cls: type[StrategyRuntime]
    spec: StrategySpec
    schema: ParamSchema | None
    params: Mapping[str, object] | None
    has_overrides: bool


@dataclass(slots=True)
class StrategyRegistry:
    version_registry: VersionRegistry = field(default_factory=_default_version_registry)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _registrations: dict[str, _Registration] = field(default_factory=dict)

    def register(
        self,
        cls: type[StrategyRuntime],
        *,
        params: str | Path | Mapping[str, object] | None = None,
        yaml_path: str | Path | None = None,
        strategy_version: str | None = None,
        code_version: str | None = None,
        description: str = "",
    ) -> StrategySpec:
        """Register a strategy class with optional parameter overrides."""

        if not inspect.isclass(cls):
            raise MarketDataValidationError("strategy must be a class")
        instance = self._build_instance(
            cls,
            params={},
            strategy_version=strategy_version or "unspecified-v1",
            code_version=code_version or "unspecified-code-v1",
        )
        if not isinstance(instance, StrategyRuntime):
            raise MarketDataValidationError(
                f"{cls.__name__} does not satisfy the StrategyRuntime protocol"
            )

        schema = self._extract_schema(cls)
        resolved_payload = self._resolve_payload(params, yaml_path)
        if resolved_payload is None:
            parameters: Mapping[str, object] | None = None
            parameter_hash = instance.parameter_hash
            has_overrides = False
        else:
            if schema is None:
                raise MarketDataValidationError(
                    f"{cls.__name__} has no ParamSchema but received parameter overrides"
                )
            loaded = load_params(resolved_payload, schema)
            parameters = loaded.params
            parameter_hash = loaded.parameter_hash
            has_overrides = True

        final_version = strategy_version or instance.version
        final_code_version = code_version or instance.code_version
        spec = StrategySpec(
            name=instance.name,
            version=final_version,
            code_version=final_code_version,
            parameter_hash=parameter_hash,
            horizon_seconds=instance.horizon_seconds,
            yaml_path=Path(yaml_path) if yaml_path is not None else None,
        )
        spec.validate()
        if spec.name in {"", None} or not spec.name.strip():
            raise MarketDataValidationError("strategy name is required")

        with self._lock:
            existing = self._registrations.get(spec.name)
            if existing is not None:
                if (
                    existing.spec.identity_key == spec.identity_key
                    and existing.cls is cls
                ):
                    return existing.spec
                raise DuplicateStrategyError(
                    f"strategy {spec.name!r} already registered with a different identity"
                )
            try:
                self.version_registry.freeze_strategy(
                    strategy_name=spec.name,
                    strategy_version=spec.version,
                    parameter_hash=spec.parameter_hash,
                    code_version=spec.code_version,
                )
            except DuplicateStrategyFreezeError as exc:
                raise DuplicateStrategyError(str(exc)) from exc
            self._registrations[spec.name] = _Registration(
                cls=cls,
                spec=spec,
                schema=schema,
                params=parameters,
                has_overrides=has_overrides,
            )
        return spec

    def get(self, name: str) -> StrategyRuntime:
        with self._lock:
            registration = self._registrations.get(name)
            if registration is None:
                raise UnknownStrategyError(f"strategy {name!r} is not registered")
            if registration.has_overrides and registration.params is not None:
                params_for_build: Mapping[str, object] = dict(registration.params)
            else:
                params_for_build = {}
            return self._build_instance(
                registration.cls,
                params=params_for_build,
                strategy_version=registration.spec.version,
                code_version=registration.spec.code_version,
            )

    def get_class(self, name: str) -> type[StrategyRuntime]:
        with self._lock:
            registration = self._registrations.get(name)
            if registration is None:
                raise UnknownStrategyError(f"strategy {name!r} is not registered")
            return registration.cls

    def get_spec(self, name: str) -> StrategySpec:
        with self._lock:
            registration = self._registrations.get(name)
            if registration is None:
                raise UnknownStrategyError(f"strategy {name!r} is not registered")
            return registration.spec

    def list_specs(self) -> tuple[StrategySpec, ...]:
        with self._lock:
            return tuple(item.spec for item in self._registrations.values())

    def names(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._registrations.keys()))

    def resolve_many(self, names: Sequence[str]) -> tuple[StrategyRuntime, ...]:
        return tuple(self.get(name) for name in names)

    @staticmethod
    def _extract_schema(cls: type[StrategyRuntime]) -> ParamSchema | None:
        candidate = getattr(cls, "param_schema", None)
        if candidate is None:
            return None
        if isinstance(candidate, classmethod):
            candidate = candidate.__func__
        if not callable(candidate):
            return None
        result = candidate()
        if isinstance(result, ParamSchema):
            return result
        return None

    @staticmethod
    def _defaults_from_runtime(instance: StrategyRuntime) -> Mapping[str, object]:
        declared = instance.declare_parameters()
        return dict(declared)

    @staticmethod
    def _resolve_payload(
        params: str | Path | Mapping[str, object] | None,
        yaml_path: str | Path | None,
    ) -> Any:
        if yaml_path is None:
            if params is None or (
                isinstance(params, Mapping) and len(params) == 0
            ):
                return None
            return params
        if params is not None and not (
            isinstance(params, Mapping) and len(params) == 0
        ):
            raise MarketDataValidationError(
                "pass only one of `params` or `yaml_path`"
            )
        return Path(yaml_path)

    @staticmethod
    def _build_instance(
        cls: type[StrategyRuntime],
        *,
        params: Mapping[str, object],
        strategy_version: str | None,
        code_version: str | None,
    ) -> StrategyRuntime:
        from_params = getattr(cls, "from_params", None)
        if params and callable(from_params):
            kwargs: dict[str, Any] = {"params": dict(params)}
            if strategy_version is not None:
                kwargs["strategy_version"] = strategy_version
            if code_version is not None:
                kwargs["code_version"] = code_version
            try:
                return from_params(**kwargs)
            except TypeError:
                pass
        if params:
            raise MarketDataValidationError(
                f"{cls.__name__} does not expose from_params; cannot apply overrides"
            )
        return cls()  # type: ignore[call-arg]


DEFAULT_REGISTRY = StrategyRegistry()


def describe_param_source(payload: Any) -> str:
    return describe_payload(payload)


__all__ = [
    "DEFAULT_REGISTRY",
    "DuplicateStrategyError",
    "StrategyRegistry",
    "UnknownStrategyError",
    "describe_param_source",
]