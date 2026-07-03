"""Strategy plugin platform.

The package exposes:

* `RuleStrategyRuntime` (frozen dataclass, backward compatible with v0)
* `StrategyRuntime` (structural Protocol)
* `StrategySpec` (static description of a registered strategy)
* `ParamSchema`, `SchemaError`, `ParamField`, `compute_parameter_hash`
* `load_params`, `LoadedParams` (YAML/JSON parameter loader)
* `StrategyRegistry`, `DEFAULT_REGISTRY` (process-local plugin registry)
* `DuplicateStrategyError`, `UnknownStrategyError` (registry errors)
* `StrategyComposer`, `ConflictPolicy`, `ComposerConflictRecord`
  (multi-strategy scheduling and conflict aggregation)

See `docs/architecture/strategy-plugin-guide.md` for the full onboarding flow.
"""

from quant_signal_system.strategies.composer import (
    ComposerConflictError,
    ComposerConflictRecord,
    ConflictPolicy,
    StrategyComposer,
    describe_composer,
    replace_candidate,
)
from quant_signal_system.strategies.metadata import StrategySpec
from quant_signal_system.strategies.protocol import StrategyRuntime
from quant_signal_system.strategies.registry import (
    DEFAULT_REGISTRY,
    DuplicateStrategyError,
    StrategyRegistry,
    UnknownStrategyError,
)
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.strategies.schema import (
    ParamField,
    ParamSchema,
    SchemaError,
    compute_parameter_hash,
)
from quant_signal_system.strategies.yaml_loader import LoadedParams, load_params

__all__ = [
    "DEFAULT_REGISTRY",
    "ComposerConflictError",
    "ComposerConflictRecord",
    "ConflictPolicy",
    "DuplicateStrategyError",
    "LoadedParams",
    "ParamField",
    "ParamSchema",
    "RuleStrategyRuntime",
    "SchemaError",
    "StrategyComposer",
    "StrategyRegistry",
    "StrategyRuntime",
    "StrategySpec",
    "UnknownStrategyError",
    "compute_parameter_hash",
    "describe_composer",
    "load_params",
    "replace_candidate",
]