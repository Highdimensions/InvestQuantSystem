"""YAML/JSON parameter loading with schema enforcement and freeze hashing.

The loader accepts three input shapes:

* a filesystem path to a YAML file (``.yaml``/``.yml``),
* an inline JSON string, or
* an already-parsed mapping.

It validates the payload against a `ParamSchema` and returns a frozen mapping
plus its deterministic hash. The hash is consumed by the registry to produce
`StrategySpec.parameter_hash`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from quant_signal_system.strategies.schema import (
    ParamSchema,
    SchemaError,
    compute_parameter_hash,
)


@dataclass(frozen=True, slots=True)
class LoadedParams:
    """Result of loading and validating one parameter payload."""

    params: Mapping[str, object]
    parameter_hash: str
    source: str

    def describe(self) -> Mapping[str, str]:
        return {
            "parameter_hash": self.parameter_hash,
            "source": self.source,
            "params": json.dumps(dict(self.params), sort_keys=True, ensure_ascii=False),
        }


def _parse_yaml(text: str) -> object:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise SchemaError(
            "PyYAML is required to load YAML parameter files; install pyyaml"
        ) from exc
    payload = yaml.safe_load(text)
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise SchemaError("YAML parameter payload must be a mapping at the top level")
    return payload


def _parse_json(text: str) -> object:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"inline JSON parameter payload is invalid: {exc}") from exc
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise SchemaError("inline JSON parameter payload must be a mapping at the top level")
    return payload


def load_params(
    payload: str | Path | Mapping[str, object],
    schema: ParamSchema,
) -> LoadedParams:
    """Load parameters from YAML path, inline JSON string, or mapping."""

    if isinstance(payload, Mapping):
        resolved = schema.validate(dict(payload))
        source = "<inline-mapping>"
    elif isinstance(payload, Path):
        text = payload.read_text(encoding="utf-8")
        resolved = schema.validate(dict(_parse_yaml(text)))  # type: ignore[arg-type]
        source = f"yaml:{payload}"
    elif isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            resolved = schema.validate({})
            source = "<inline-empty>"
        elif stripped[:1] in ("{", "["):
            resolved = schema.validate(dict(_parse_json(stripped)))  # type: ignore[arg-type]
            source = "<inline-json>"
        else:
            path = Path(stripped)
            if not path.exists():
                raise SchemaError(f"parameter source path does not exist: {path}")
            text = path.read_text(encoding="utf-8")
            resolved = schema.validate(dict(_parse_yaml(text)))  # type: ignore[arg-type]
            source = f"yaml:{path}"
    else:
        raise SchemaError(f"unsupported parameter payload type: {type(payload).__name__}")

    frozen = MappingProxyType(dict(resolved))
    return LoadedParams(
        params=frozen,
        parameter_hash=compute_parameter_hash(resolved),
        source=source,
    )


def describe_payload(payload: Any) -> str:
    if isinstance(payload, Path):
        return f"yaml:{payload}"
    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return "<inline-empty>"
        if stripped.startswith("{"):
            return "<inline-json>"
        return f"yaml:{stripped}"
    if isinstance(payload, Mapping):
        return "<inline-mapping>"
    return repr(payload)