# Test And Evaluation Plan Template

## 1. Scope

- System under test:
- Components included:
- Components excluded:
- Primary correctness risks:
- Primary operational risks:
- Required confidence before release:

## 2. Test Surfaces

Cover these surfaces when applicable:

- Pure calculations
- Stateful strategy logic
- Data normalization
- Clock and time zone behavior
- Persistence and idempotency
- Historical replay
- Backtest engine
- Delayed evaluator
- Paper portfolio
- Live shadow path
- Metrics and reports
- Recovery after interruption

## 3. Unit Tests

For each unit:

- Function or class:
- Fixture:
- Assertion:
- Boundary cases:
- Error cases:
- Determinism requirements:

Quant-specific examples:

- Moving average windows do not include future bars.
- Volume ratio uses only completed data.
- Triple-barrier label picks the first barrier hit.
- Directional return handles Buy, Hold, and Sell consistently.
- MFE and MAE are direction-adjusted.

## 4. Contract Tests

Validate schemas and interfaces:

- `SignalEvent` required fields
- Market bar schema
- Evaluation result schema
- Strategy input/output contract
- Repository idempotency behavior
- API response compatibility
- Event or file version compatibility

Include negative tests for missing fields, invalid timestamps, duplicate IDs, and incompatible versions.

## 5. Data Replay Tests

Define deterministic replay fixtures:

- Tiny hand-built fixture for edge cases
- Known historical day fixture
- Missing bar fixture
- Duplicate tick fixture
- Delayed data fixture
- Halt or limit fixture

Assertions:

- Same input produces identical signals.
- Signal count and IDs match golden output.
- Feature snapshots match expected values.
- Replay can resume from checkpoint.
- Replay does not mutate historical signal records.

## 6. Backtest Correctness Tests

Validate:

- No look-ahead in features or labels
- Execution price is available only after signal time
- Fees, taxes, spread, slippage, and delay are applied
- Position state transitions are correct
- Repeated signals are handled as designed
- Limit-up, limit-down, halt, and insufficient-volume cases behave correctly
- Metrics are direction-adjusted and cost-adjusted

Golden cases:

```text
one winning Buy
one losing Buy
one Sell-as-risk-reduction signal
one Hold signal
one signal blocked by execution constraints
one repeated signal while already in position
```

## 7. Realtime Consistency Tests

Compare live shadow and replay:

- Same strategy version
- Same feature version
- Same parameter hash
- Same input bars after normalization
- Same clock interpretation
- Same execution simulation

Metrics:

- Signal match rate
- Timestamp delta
- Feature delta
- Score delta
- Missing signal count
- Extra signal count
- Latency distribution

Pass criteria should name acceptable tolerances. For deterministic rule strategies, unexplained signal mismatches should normally be zero.

## 8. Delayed Evaluation Tests

Validate:

- Pending evaluations are discovered after restart.
- Each horizon is evaluated exactly once.
- Late-arriving market data is handled explicitly.
- Evaluation price is realistic and available at evaluation time.
- MFE, MAE, fixed-horizon return, and triple-barrier result are reproducible.
- Partial failure does not create duplicate or missing evaluations.

## 9. Failure Recovery Tests

Inject failures at:

- Market data ingestion
- Normalization
- Feature calculation
- Signal persistence
- Evaluation scheduling
- Evaluation write
- Dashboard or report generation
- Process shutdown and restart

For each failure:

- Expected detection:
- Expected retry or quarantine:
- Idempotency key:
- State after resume:
- Data loss expectation:
- Alert expectation:

## 10. Performance And Latency Tests

Measure:

- Data arrival to normalized bar
- Normalized bar to feature update
- Feature update to signal generated
- Signal generated to persisted
- Signal persisted to dashboard visible
- Evaluation due time to evaluation persisted

Include percentile targets, not just averages.

## 11. Evaluation Metrics

System correctness metrics:

- Replay determinism
- Live/replay match rate
- Evaluation completeness
- Duplicate rate
- Missing-data rate
- Recovery success rate
- Latency percentiles

Signal quality metrics:

- Hit rate
- Average and median directional return
- Net return after costs
- MFE and MAE
- Profit factor
- Expected value
- Max consecutive losses
- Confidence calibration

Keep system correctness and signal profitability separate in reports.

## 12. Release Gate

Before release or promotion:

- Unit and contract tests pass.
- Golden replay output is unchanged or deliberately approved.
- Backtest bias checks pass.
- Recovery tests pass.
- Shadow run has acceptable live/replay consistency.
- Dashboards and alerts exist for critical paths.
- Known residual risks are documented.

## 13. Test Plan Output Format

Use this concise format:

```text
Test area:
Purpose:
Fixture/data:
Steps:
Assertions:
Pass criteria:
Failure diagnostics:
Owner:
Automation status:
```
