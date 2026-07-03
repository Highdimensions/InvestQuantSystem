"""Shadow/replay reconciliation for signal outputs."""

from __future__ import annotations

from dataclasses import dataclass

from quant_signal_system.contracts.signals import SignalEvent


@dataclass(frozen=True, slots=True)
class SignalReconciliationReport:
    missing_in_shadow: tuple[str, ...]
    extra_in_shadow: tuple[str, ...]
    direction_mismatches: tuple[str, ...]

    @property
    def unexplained_differences(self) -> int:
        return len(self.missing_in_shadow) + len(self.extra_in_shadow) + len(self.direction_mismatches)


class ShadowRunComparator:
    def compare(
        self,
        *,
        replay_signals: list[SignalEvent],
        shadow_signals: list[SignalEvent],
    ) -> SignalReconciliationReport:
        replay = {signal.signal_id: signal for signal in replay_signals}
        shadow = {signal.signal_id: signal for signal in shadow_signals}
        missing = tuple(sorted(set(replay) - set(shadow)))
        extra = tuple(sorted(set(shadow) - set(replay)))
        mismatches = tuple(
            sorted(
                signal_id
                for signal_id in set(replay) & set(shadow)
                if replay[signal_id].direction != shadow[signal_id].direction
            )
        )
        return SignalReconciliationReport(missing, extra, mismatches)

