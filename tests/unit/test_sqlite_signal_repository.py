from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from quant_signal_system.contracts.evaluation import EvaluationPolicy
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.evaluation.evaluator import SignalEvaluator
from quant_signal_system.evaluation.scheduler import EvaluationScheduler
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.market_data.repository import InMemoryMarketDataRepository
from quant_signal_system.signals.repository import SignalConflictError
from quant_signal_system.signals.service import SignalService
from quant_signal_system.signals.sqlite_repository import SQLiteSignalRepository
from quant_signal_system.strategies.runtime import RuleStrategyRuntime
from quant_signal_system.time.clock import FrozenClock
from quant_signal_system.time.trading_calendar import SimpleAshareTradingCalendar


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def bar(time_value: str, close: str, volume: str = "100") -> MarketBar:
    end = utc(time_value)
    price = Decimal(close)
    return MarketBar(
        schema_version="market-bar-v1",
        symbol="000001",
        timeframe="1m",
        bar_start_time=end - timedelta(minutes=1),
        bar_end_time=end,
        market_data_time=end,
        ingest_time=end,
        open_price=price,
        high_price=price + Decimal("0.10"),
        low_price=price - Decimal("0.10"),
        close_price=price,
        volume=Decimal(volume),
        amount=price * Decimal(volume),
        turnover=None,
        trading_status=TradingStatus.TRADING,
        is_closed=True,
        bar_close_time=end,
        source="AKShare",
        data_source_version="akshare-exploration-v1",
        as_of_version="asof-research-v1",
    )


def make_signal(repo: SQLiteSignalRepository):
    clock = FrozenClock(utc("2024-07-03T01:35:00+00:00"))
    feature_engine = RollingFeatureEngine(clock=clock)
    signal_service = SignalService(clock)
    strategy = RuleStrategyRuntime()
    candidate = None
    for item in [
        bar("2024-07-03T01:31:00+00:00", "10.00", "100"),
        bar("2024-07-03T01:32:00+00:00", "10.10", "100"),
        bar("2024-07-03T01:33:00+00:00", "10.30", "300"),
    ]:
        snapshot = feature_engine.update_closed_bar(item)
        candidate = strategy.on_bar(item, snapshot)
    assert candidate is not None
    signal = signal_service.create_event(candidate)
    repo.append_signal(signal)
    return signal, clock


def test_sqlite_signal_repository_is_append_only(tmp_path) -> None:
    repo = SQLiteSignalRepository(tmp_path / "signals.db")
    signal, _ = make_signal(repo)

    assert repo.append_signal(signal) == signal.signal_id
    assert repo.get_signal(signal.signal_id) == signal
    assert repo.list_signals(symbol="000001") == [signal]
    assert repo.strategy_counts()[0]["strategy_version"] == "baseline-rules-v1"

    changed = replace(signal, score=Decimal("0.99"))
    with pytest.raises(SignalConflictError):
        repo.append_signal(changed)


def test_sqlite_signal_repository_persists_tasks_and_evaluations(tmp_path) -> None:
    signal_repo = SQLiteSignalRepository(tmp_path / "signals.db")
    signal, clock = make_signal(signal_repo)
    market_repo = InMemoryMarketDataRepository()
    for item in [
        bar("2024-07-03T01:36:00+00:00", "10.40", "200"),
        bar("2024-07-03T01:37:00+00:00", "10.50", "200"),
        bar("2024-07-03T01:38:00+00:00", "10.55", "200"),
        bar("2024-07-03T01:39:00+00:00", "10.60", "200"),
        bar("2024-07-03T01:40:00+00:00", "10.70", "200"),
    ]:
        market_repo.save_bar(item)

    policy = EvaluationPolicy(horizons_seconds=(300,))
    scheduler = EvaluationScheduler(signal_repo, clock, SimpleAshareTradingCalendar(), policy)
    task = scheduler.create_tasks_for_signal(signal)[0]
    clock.advance(timedelta(minutes=6))

    due = signal_repo.find_due_tasks(clock.now())
    assert due == [task]
    claimed = scheduler.claim(due[0], worker_id="test-worker")
    evaluation = SignalEvaluator(signal_repo, market_repo, clock, policy=policy).evaluate(claimed)

    assert signal_repo.upsert_evaluation(evaluation) == "inserted"
    assert signal_repo.upsert_evaluation(evaluation) == "duplicate"
    signal_repo.complete_task(claimed.task_key)
    assert signal_repo.list_evaluations(signal_ids=(signal.signal_id,)) == [evaluation]
