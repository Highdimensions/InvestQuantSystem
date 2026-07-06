# Quant Signal System Design And Review Template

## 1. System Positioning

Clarify whether the system is for:

- Research only
- Historical replay
- Backtesting
- Real-time shadow running
- Paper trading
- Live trading preparation

Default stance: validate signals and infrastructure before any real order execution.

## 2. Market And Horizon

- Market:
- Symbols or universe:
- Bar or tick granularity:
- Signal horizon:
- Trading session calendar:
- Time zone:
- Halt, limit-up, and limit-down assumptions:
- Execution assumption:

## 3. Core Architecture

Recommended first version:

```text
Market data
  -> data normalizer
  -> incremental feature engine
  -> market regime engine
  -> signal engine
  -> SignalEvent store
  -> delayed evaluator
  -> metrics and dashboard
```

Optional components:

- Historical replay source
- Live data source
- Paper portfolio
- Backtest runner
- Evaluation worker
- Shadow-run comparator

## 4. SignalEvent Contract

Every signal should be immutable and append-only.

Required fields:

- `signal_id`
- `symbol`
- `event_time`
- `market_data_time`
- `executable_time`
- `reference_price`
- `executable_price`
- `direction`: `1`, `0`, or `-1`
- `score`
- `confidence`
- `horizon_seconds`
- `reason_codes`
- `strategy_name`
- `strategy_version`
- `feature_snapshot`
- `feature_version`
- `code_version`
- `parameter_hash`

Review questions:

- Can the signal be reproduced later?
- Does it record the exact information visible at decision time?
- Does it distinguish observed price from executable price?
- Are historical signals never modified after strategy changes?

## 5. Time And Price Semantics

Track at least three clocks:

```text
market_data_time: time represented by the market data
event_time: time the strategy produced the signal
executable_time: earliest realistic execution time
```

Reject designs that use:

- Future high or low inside the current bar
- Final volume of an unfinished bar
- Close price before the bar is actually closed
- Future corporate action or index membership data
- End-of-day data for intraday decisions

## 6. Feature Engineering

Baseline feature groups:

- Short-window returns
- Moving averages and slopes
- Volume ratios and amount changes
- Intraday high/low position
- Volatility and true range
- Relative strength versus sector and index
- Market regime labels

Each feature needs:

- Input data source
- Lookback window
- Boundary behavior
- Missing data behavior
- Versioning
- Replay/live consistency test

## 7. Strategy Design

Start with explainable baselines:

- Volume breakout
- Pullback on shrinking volume
- Spike-and-fade sell/reduce signal
- Overbought/oversold in range-bound regimes

For each strategy:

- Trigger conditions:
- Direction:
- Score formula:
- Confidence formula:
- Horizon:
- Reason codes:
- Invalid condition:
- Market regimes where it is expected to work:
- Market regimes where it should be disabled:

Avoid starting with complex machine learning models before the data, replay, execution simulation, and evaluator are proven correct.

## 8. Historical Replay And Backtesting

Design principle: historical and live paths should share strategy code.

```text
HistoricalDataSource or LiveDataSource
  -> same normalizer
  -> same feature engine
  -> same Strategy.on_bar / Strategy.on_tick
  -> same SignalEvent contract
```

Backtest must model:

- Transaction fees
- Taxes
- Bid/ask spread
- Slippage
- Signal delay
- Limit-up and limit-down inability to trade
- Halts
- Insufficient volume
- Position state
- Repeated signals

## 9. Bias Controls

Check:

- Look-ahead bias
- Data leakage
- Survivorship bias
- Parameter overfitting
- Cost underestimation
- Selective reporting
- Replay/live divergence

Require out-of-sample or walk-forward validation before claiming signal quality.

## 10. Delayed Evaluation

Evaluate each signal at fixed horizons:

- 1 minute
- 5 minutes
- 10 minutes
- 15 minutes
- 30 minutes
- 60 minutes
- Close
- Next open if relevant

Metrics:

- Directional return
- Net return after costs
- Hit rate
- Median return
- MFE
- MAE
- Time to MFE
- Time to MAE
- Triple-barrier label
- Profit factor
- Expected value
- Maximum consecutive losses

Group metrics by:

- Time of day
- Market regime
- Sector regime
- Volatility bucket
- Volume bucket
- Signal score bucket
- Confidence bucket
- Strategy version

## 11. Real-Time Shadow Run

Shadow run records:

- Data arrival time
- Market data source timestamp
- Normalization time
- Feature calculation latency
- Signal generation time
- Persist latency
- Simulated executable price
- Future evaluation result

Compare:

- Live shadow output
- Same-period historical replay output
- Strategy version
- Feature version
- K-line boundaries
- Missing-data behavior
- Execution price simulation

Any unexplained mismatch is a system defect until proven otherwise.

## 12. Minimal Viable Build

Recommended first milestone:

- One symbol
- 1-minute bars
- Three rule strategies
- SQLite or a single local database
- Append-only signal table
- Delayed evaluator
- 5, 15, 30, and 60 minute evaluation
- Simple dashboard or report
- Replay/live comparison report

## 13. Review Checklist

- Signals are immutable and versioned.
- Time and price semantics prevent look-ahead.
- Replay and live share strategy logic.
- Evaluation uses executable prices and costs.
- Metrics include downside behavior, not only win rate.
- Shadow run is required before real trading.
- System correctness is separated from signal profitability.
