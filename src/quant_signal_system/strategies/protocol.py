"""Structural typing contract for strategy runtimes.

A `StrategyRuntime` is the smallest object the rest of the system depends on. It
must expose a stable identity (name/version/code_version/parameter_hash) and
turn a closed `MarketBar` plus its `FeatureSnapshot` into at most one
`SignalCandidate`.

The protocol is deliberately a `typing.Protocol` rather than an ABC:

* Existing strategies such as `RuleStrategyRuntime` are frozen dataclasses and
  do not need to inherit from a base class.
* New strategies only need to expose the listed attributes and implement
  `on_bar` to satisfy the contract.
* `isinstance(value, StrategyRuntime)` is enabled by `@runtime_checkable`
  for tests and adapters that need structural checks.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from quant_signal_system.contracts.features import FeatureSnapshot, MarketRegime
from quant_signal_system.contracts.market import MarketBar
from quant_signal_system.contracts.signals import SignalCandidate


@runtime_checkable
class StrategyRuntime(Protocol):
    """The structural contract every strategy runtime must satisfy."""

    @property
    def name(self) -> str:
        """Stable identifier used by the registry (e.g. ``"baseline_rules"``)."""

    @property
    def version(self) -> str:
        """Strategy-level version label (changes when logic changes)."""

    @property
    def code_version(self) -> str:
        """Code-level version label (changes when implementation changes)."""

    @property
    def parameter_hash(self) -> str:
        """Stable digest of effective parameters; constant for identical config."""

    @property
    def horizon_seconds(self) -> int:
        """Default evaluation horizon produced by this strategy."""

    def on_bar(
        self,
        bar: MarketBar,
        snapshot: FeatureSnapshot,
        regime: MarketRegime | None = ...,
    ) -> SignalCandidate | None:
        """Produce at most one candidate per closed bar, or ``None`` to abstain."""

    def declare_parameters(self) -> tuple[tuple[str, object], ...]:
        """Return the effective parameter key/value pairs.

        Used by the registry to compute ``parameter_hash`` and to validate
        YAML/JSON overrides against the strategy's declared schema.
        """