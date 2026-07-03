"""Parameter schema declarations and parameter-hash helpers.

Each strategy declares its effective parameters through `ParamSchema`. The
schema rejects unknown fields (so YAML/JSON typos surface at load time) and
fills in declared defaults when a field is omitted.

`compute_parameter_hash` produces a stable digest of the resolved parameter
mapping. The digest is part of the strategy's frozen identity and is embedded
in every emitted `SignalCandidate.parameter_hash`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from quant_signal_system.contracts.market import MarketDataValidationError


class SchemaError(MarketDataValidationError):
    """Raised when parameters violate the declared schema."""


@dataclass(frozen=True, slots=True)
class ParamField:
    """Declaration of one configurable parameter."""

    name: str
    type_: type
    default: object
    description: str = ""

    def coerce(self, raw: object) -> object:
        if raw is None:
            return self.default
        if isinstance(raw, self.type_):
            return raw
        if self.type_ is bool and isinstance(raw, int):
            if raw not in (0, 1):
                raise SchemaError(f"{self.name} must be boolean-compatible integer 0/1")
            return bool(raw)
        if self.type_ in (int, float, str) and not isinstance(raw, bool):
            try:
                return self.type_(raw)
            except (TypeError, ValueError) as exc:
                raise SchemaError(
                    f"{self.name} cannot be coerced to {self.type_.__name__}: {exc}"
                ) from exc
        raise SchemaError(
            f"{self.name} expected {self.type_.__name__}, got {type(raw).__name__}"
        )


@dataclass(frozen=True, slots=True)
class ParamSchema:
    """Ordered schema of declared parameters.

    A schema with no fields is valid: it expresses a parameterless strategy.
    """

    fields: tuple[ParamField, ...]
    extras_allowed: bool = False

    @classmethod
    def of(cls, *fields: ParamField | tuple[str, type, object] | tuple[str, type, object, str]) -> "ParamSchema":
        """Build a schema from positional tuples or `ParamField` entries.

        Each positional argument can be:

        * a `ParamField`, or
        * a ``(name, type, default)`` tuple, or
        * a ``(name, type, default, description)`` tuple.
        """

        resolved: list[ParamField] = []
        for item in fields:
            if isinstance(item, ParamField):
                resolved.append(item)
                continue
            if len(item) == 3:
                resolved.append(ParamField(name=item[0], type_=item[1], default=item[2]))
            elif len(item) == 4:
                resolved.append(
                    ParamField(name=item[0], type_=item[1], default=item[2], description=item[3])
                )
            else:
                raise SchemaError("ParamSchema field must be ParamField or 3/4-tuple")
        names = [field.name for field in resolved]
        if len(names) != len(set(names)):
            raise SchemaError("ParamSchema field names must be unique")
        return cls(fields=tuple(resolved), extras_allowed=False)

    def field_names(self) -> tuple[str, ...]:
        return tuple(field.name for field in self.fields)

    def defaults(self) -> Mapping[str, object]:
        return {field.name: field.default for field in self.fields}

    def validate(self, params: Mapping[str, object]) -> Mapping[str, object]:
        """Coerce inputs against the schema; raise on unknown fields."""

        if not self.extras_allowed:
            unknown = set(params.keys()) - set(self.field_names())
            if unknown:
                raise SchemaError(f"unknown parameter(s) for schema: {sorted(unknown)}")
        resolved: dict[str, object] = {}
        for field in self.fields:
            if field.name in params:
                resolved[field.name] = field.coerce(params[field.name])
            else:
                resolved[field.name] = field.default
        return resolved


def compute_parameter_hash(params: Mapping[str, object]) -> str:
    """Stable sha256 digest of the parameter mapping (sorted keys, JSON form)."""

    serialisable: dict[str, Any] = {}
    for key in sorted(params):
        value = params[key]
        if isinstance(value, bool):
            serialisable[key] = int(value)
        elif isinstance(value, (str, int, float)) or value is None:
            serialisable[key] = value
        else:
            serialisable[key] = repr(value)
    encoded = json.dumps(serialisable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()