"""Signal and portfolio metrics aggregation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from quant_signal_system.contracts.evaluation import SignalEvaluation
from quant_signal_system.contracts.signals import SignalEvent
from quant_signal_system.portfolio.ledger import PortfolioLedger


@dataclass(frozen=True, slots=True)
class SignalMetrics:
    """Aggregated signal metrics for one bucket."""

    strategy_name: str
    strategy_version: str
    symbol: str
    direction: int
    reason_code: str | None
    year: int
    month: int

    sample_count: int = 0
    unexecutable_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    avg_net_return: Decimal = Decimal("0")
    std_net_return: Decimal = Decimal("0")
    avg_mfe: Decimal = Decimal("0")
    avg_mae: Decimal = Decimal("0")
    mfe_mae_ratio: Decimal | None = None

    @property
    def win_rate(self) -> Decimal:
        if self.sample_count == 0:
            return Decimal("0")
        return Decimal(self.win_count) / Decimal(self.sample_count)


def _bucket_key(signal: SignalEvent, evaluation: SignalEvaluation | None, bucket_date: date) -> tuple:
    return (
        signal.strategy_name,
        signal.strategy_version,
        signal.symbol,
        int(signal.direction),
        evaluation.reason_codes[0] if (evaluation and evaluation.reason_codes) else None,
        bucket_date.year,
        bucket_date.month,
    )


def _aggregate(values: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Return (mean, std) for a list of Decimals."""
    if not values:
        return Decimal("0"), Decimal("0")
    mean = sum(values) / Decimal(len(values))
    if len(values) < 2:
        return mean, Decimal("0")
    variance = sum((v - mean) ** 2 for v in values) / Decimal(len(values))
    std = Decimal(str(float(variance) ** 0.5))
    return mean, std


def aggregate_signal_metrics(
    signals: Iterable[SignalEvent],
    evaluations: dict[str, SignalEvaluation],
    evaluation_dates: dict[str, date],
) -> list[SignalMetrics]:
    """Aggregate SignalMetrics by (strategy, version, symbol, direction, reason_code, year, month)."""
    buckets: dict[tuple, list[tuple[SignalEvent, SignalEvaluation | None]]] = defaultdict(list)

    for signal in signals:
        ev = evaluations.get(signal.signal_id)
        bucket_date = evaluation_dates.get(signal.signal_id, date.today())
        key = _bucket_key(signal, ev, bucket_date)
        buckets[key].append((signal, ev))

    results: list[SignalMetrics] = []
    for key, items in buckets.items():
        strategy_name, strategy_version, symbol, direction, reason_code, year, month = key
        net_returns: list[Decimal] = []
        mfes: list[Decimal] = []
        maes: list[Decimal] = []
        win_count = 0
        loss_count = 0
        unexecutable_count = 0

        for signal, ev in items:
            if ev is None or ev.net_return is None:
                unexecutable_count += 1
                continue
            net_returns.append(ev.net_return)
            if ev.mfe is not None:
                mfes.append(ev.mfe)
            if ev.mae is not None:
                maes.append(ev.mae)
            if ev.net_return > 0:
                win_count += 1
            elif ev.net_return < 0:
                loss_count += 1

        avg_net, std_net = _aggregate(net_returns)
        avg_mfe, _ = _aggregate(mfes)
        avg_mae, _ = _aggregate(maes)
        mfe_mae_ratio = None
        if avg_mae != 0:
            mfe_mae_ratio = abs(avg_mfe / avg_mae)

        results.append(SignalMetrics(
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=symbol,
            direction=direction,
            reason_code=reason_code,
            year=year,
            month=month,
            sample_count=len(items),
            unexecutable_count=unexecutable_count,
            win_count=win_count,
            loss_count=loss_count,
            avg_net_return=avg_net,
            std_net_return=std_net,
            avg_mfe=avg_mfe,
            avg_mae=avg_mae,
            mfe_mae_ratio=mfe_mae_ratio,
        ))

    return results


@dataclass(frozen=True, slots=True)
class PortfolioMetrics:
    """Portfolio-level performance metrics."""

    initial_cash: Decimal
    final_value: Decimal
    total_return: Decimal
    annualized_return: Decimal
    sharpe_ratio: Decimal | None
    max_drawdown: Decimal
    calmar_ratio: Decimal | None
    turnover: Decimal
    trade_count: int
    days: int


def compute_portfolio_metrics(
    ledger: PortfolioLedger,
    daily_values: dict[date, Decimal],
    risk_free_rate: Decimal = Decimal("0.02"),
) -> PortfolioMetrics:
    """Compute portfolio-level metrics from ledger and daily values."""
    initial = ledger.initial_cash
    final = daily_values[max(daily_values.keys())] if daily_values else ledger.cash
    total_return = (final - initial) / initial if initial != 0 else Decimal("0")

    values = [daily_values[d] for d in sorted(daily_values)]
    days = len(values)
    if days < 2:
        return PortfolioMetrics(
            initial_cash=initial,
            final_value=final,
            total_return=total_return,
            annualized_return=total_return,
            sharpe_ratio=None,
            max_drawdown=Decimal("0"),
            calmar_ratio=None,
            turnover=Decimal("0"),
            trade_count=ledger.pending_settlement_count(),
            days=days,
        )

    annualized_return = total_return / Decimal(days) * Decimal("252")
    returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
    avg_ret = sum(returns) / Decimal(len(returns))
    variance = sum((r - avg_ret) ** 2 for r in returns) / Decimal(len(returns))
    std_ret = Decimal(str(float(variance) ** 0.5))
    sharpe = (avg_ret - risk_free_rate / Decimal("252")) / std_ret if std_ret != 0 else None

    peak = values[0]
    max_dd = Decimal("0")
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak
        if dd > max_dd:
            max_dd = dd

    calmar = total_return / max_dd if max_dd != 0 else None

    return PortfolioMetrics(
        initial_cash=initial,
        final_value=final,
        total_return=total_return,
        annualized_return=annualized_return,
        sharpe_ratio=sharpe,
        max_drawdown=max_dd,
        calmar_ratio=calmar,
        turnover=Decimal("0"),
        trade_count=ledger.pending_settlement_count(),
        days=days,
    )
