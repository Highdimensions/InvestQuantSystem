from datetime import datetime, timedelta, timezone
from decimal import Decimal

from quant_signal_system.backtest.runner import BacktestRunner
from quant_signal_system.contracts.evaluation import EvaluationPolicy, EvaluationTaskStatus
from quant_signal_system.contracts.market import MarketBar, TradingStatus
from quant_signal_system.evaluation.evaluator import SignalEvaluator
from quant_signal_system.evaluation.scheduler import EvaluationScheduler
from quant_signal_system.features.engine import RollingFeatureEngine
from quant_signal_system.market_data.repository import InMemoryMarketDataRepository
from quant_signal_system.portfolio.paper import PaperPortfolio
from quant_signal_system.reporting.reconciliation import ShadowRunComparator
from quant_signal_system.reporting.reports import EvaluationReportBuilder
from quant_signal_system.signals.repository import InMemorySignalRepository
from quant_signal_system.signals.service import SignalService
from quant_signal_system.strategies.composer import StrategyComposer
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


def test_research_pipeline_generates_evaluates_reports_and_paper_fills() -> None:
    clock = FrozenClock(utc("2024-07-03T01:35:00+00:00"))
    signal_repo = InMemorySignalRepository()
    market_repo = InMemoryMarketDataRepository()
    feature_engine = RollingFeatureEngine(clock=clock)
    signal_service = SignalService(clock)
    strategy = RuleStrategyRuntime()
    composer = StrategyComposer.single(strategy)
    runner = BacktestRunner(feature_engine, composer, signal_service, signal_repo)

    strategy_bars = [
        bar("2024-07-03T01:31:00+00:00", "10.00", "100"),
        bar("2024-07-03T01:32:00+00:00", "10.10", "100"),
        bar("2024-07-03T01:33:00+00:00", "10.30", "300"),
    ]
    evaluation_bars = [
        bar("2024-07-03T01:36:00+00:00", "10.40", "200"),
        bar("2024-07-03T01:37:00+00:00", "10.50", "200"),
        bar("2024-07-03T01:38:00+00:00", "10.55", "200"),
        bar("2024-07-03T01:39:00+00:00", "10.60", "200"),
        bar("2024-07-03T01:40:00+00:00", "10.70", "200"),
    ]
    for item in strategy_bars + evaluation_bars:
        market_repo.save_bar(item)

    result = runner.run_bars(strategy_bars)
    assert result.signals_created == 1

    signal = signal_repo.get_signal(result.signal_ids[0])
    policy = EvaluationPolicy(horizons_seconds=(300,))
    scheduler = EvaluationScheduler(
        signal_repo,
        clock,
        SimpleAshareTradingCalendar(),
        policy,
    )
    tasks = scheduler.create_tasks_for_signal(signal)
    assert len(tasks) == 1

    clock.advance(timedelta(minutes=6))
    due = scheduler.find_due_tasks()[0]
    claimed = scheduler.claim(due, worker_id="test-worker")
    evaluation = SignalEvaluator(signal_repo, market_repo, clock, policy=policy).evaluate(claimed)
    signal_repo.upsert_evaluation(evaluation)
    signal_repo.complete_task(claimed.task_key)

    assert evaluation.status == EvaluationTaskStatus.COMPLETED
    assert evaluation.net_return is not None
    assert signal_repo.list_evaluations() == [evaluation]

    report = EvaluationReportBuilder().build(signal_repo.list_evaluations())
    assert report.total == 1
    assert "不构成收益承诺" in report.to_markdown()

    paper = PaperPortfolio(portfolio_id="p1", paper_run_id="paper-v1")
    events = paper.apply_signal(signal, fill_price=Decimal("10.40"))
    assert len(events) == 2
    assert paper.position("000001", Decimal("10.70")).quantity == Decimal("100")

    recon = ShadowRunComparator().compare(replay_signals=[signal], shadow_signals=[signal])
    assert recon.unexplained_differences == 0

