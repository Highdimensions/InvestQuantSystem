"""Triple barrier configuration and conflict resolution.

Implements the triple barrier labelling scheme defined in
``docs/architecture/testing-and-evaluation.md`` Section 3.2:
- Profit-take (TP) barrier
- Stop-loss (SL) barrier
- Time barrier (max holding period)

The configured ``BarrierConflictPolicy`` determines how simultaneous TP / SL
triggers on the same OHLC bar are resolved. The default ``AMBIGUOUS``
behaviour matches the existing Evaluator, with ``CONSERVATIVE`` selecting the
unfavorable outcome to avoid overstating strategy performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from quant_signal_system.contracts.evaluation import BarrierConflictPolicy


# Outcome constants for triple barrier label.
# Positive value indicates profit-take triggered first, negative indicates
# stop-loss triggered first, zero indicates time barrier reached without
# either price barrier triggering.
TRIPLE_BARRIER_TIME_ONLY = 0
TRIPLE_BARRIER_PROFIT_TAKE = 1
TRIPLE_BARRIER_STOP_LOSS = -1
TRIPLE_BARRIER_AMBIGUOUS = 2


@dataclass(frozen=True, slots=True)
class TripleBarrierConfig:
    """Triple-barrier evaluation parameters.

    All ratio values are decimal fractions of the executable price, e.g.
    ``Decimal("0.02")`` represents a 2 % profit-take barrier.
    """

    barrier_config_version: str = "triple-barrier-v1"
    profit_barrier_ratio: Decimal | None = None
    loss_barrier_ratio: Decimal | None = None
    time_barrier_seconds: int | None = None
    conflict_policy: BarrierConflictPolicy = BarrierConflictPolicy.AMBIGUOUS

    def validate(self) -> None:
        """Validate the barrier parameters."""
        if self.profit_barrier_ratio is not None and self.profit_barrier_ratio <= 0:
            raise ValueError("profit_barrier_ratio must be positive")
        if self.loss_barrier_ratio is not None and self.loss_barrier_ratio >= 0:
            raise ValueError("loss_barrier_ratio must be negative")
        if self.time_barrier_seconds is not None and self.time_barrier_seconds <= 0:
            raise ValueError("time_barrier_seconds must be positive")

    @property
    def has_price_barriers(self) -> bool:
        """Return True if either TP or SL ratio is configured."""
        return self.profit_barrier_ratio is not None or self.loss_barrier_ratio is not None


def detect_first_barrier_hit(
    executable_price: Decimal,
    direction: int,
    path_bars: list,
    config: TripleBarrierConfig,
) -> tuple[int, int | None]:
    """Walk the OHLC path and report the first barrier to trigger.

    Parameters
    ----------
    executable_price:
        The price at which the position was opened.
    direction:
        ``+1`` for BUY (long) or ``-1`` for SELL (risk-reducing short bias).
    path_bars:
        Sequence of OHLC bars in chronological order.
    config:
        The triple barrier configuration.

    Returns
    -------
    tuple ``(barrier_label, time_to_hit_seconds)`` where ``barrier_label`` is one of
    :data:`TRIPLE_BARRIER_PROFIT_TAKE`, :data:`TRIPLE_BARRIER_STOP_LOSS`,
    :data:`TRIPLE_BARRIER_AMBIGUOUS` or :data:`TRIPLE_BARRIER_TIME_ONLY`. The
    ``time_to_hit_seconds`` is the seconds elapsed from the first path bar to the
    triggering bar, or ``None`` when no bar triggered any barrier.
    """
    if not path_bars:
        return TRIPLE_BARRIER_TIME_ONLY, None

    tp_ratio = config.profit_barrier_ratio
    sl_ratio = config.loss_barrier_ratio
    time_limit = config.time_barrier_seconds

    tp_price: Decimal | None = None
    sl_price: Decimal | None = None
    if direction == 1:
        if tp_ratio is not None:
            tp_price = executable_price * (Decimal("1") + tp_ratio)
        if sl_ratio is not None:
            sl_price = executable_price * (Decimal("1") + sl_ratio)
    else:
        # SELL signals are risk-reducing: TP fires when price drops, SL fires
        # when price rises.
        if tp_ratio is not None:
            tp_price = executable_price * (Decimal("1") - tp_ratio)
        if sl_ratio is not None:
            sl_price = executable_price * (Decimal("1") - sl_ratio)

    base_time = path_bars[0].market_data_time

    for idx, bar in enumerate(path_bars):
        elapsed = int((bar.market_data_time - base_time).total_seconds())

        tp_hit = False
        sl_hit = False
        if direction == 1:
            if tp_price is not None and bar.high_price >= tp_price:
                tp_hit = True
            if sl_price is not None and bar.low_price <= sl_price:
                sl_hit = True
        else:
            if tp_price is not None and bar.low_price <= tp_price:
                tp_hit = True
            if sl_price is not None and bar.high_price >= sl_price:
                sl_hit = True

        if tp_hit and sl_hit:
            if config.conflict_policy == BarrierConflictPolicy.CONSERVATIVE:
                # Conservative: assume stop-loss triggered first.
                return TRIPLE_BARRIER_STOP_LOSS, elapsed
            return TRIPLE_BARRIER_AMBIGUOUS, elapsed
        if tp_hit:
            return TRIPLE_BARRIER_PROFIT_TAKE, elapsed
        if sl_hit:
            return TRIPLE_BARRIER_STOP_LOSS, elapsed

        if time_limit is not None and elapsed >= time_limit:
            return TRIPLE_BARRIER_TIME_ONLY, elapsed

    return TRIPLE_BARRIER_TIME_ONLY, None