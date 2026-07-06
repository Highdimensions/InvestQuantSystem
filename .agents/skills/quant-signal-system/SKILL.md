---
name: quant-signal-system
description: "Design or review short-horizon quantitative signal systems, including signal event schemas, market data normalization, feature engines, historical replay, backtesting, latency evaluation, delayed evaluation, paper portfolios, and real-time shadow runs. Use when the user asks about intraday alpha signals, Buy/Sell/Hold recommendations, replay-vs-live consistency, backtest bias control, model evaluation, or quant signal platform architecture. Do not use for general investing advice, portfolio recommendations, broker execution automation, long-term fundamental analysis, or legal/financial advice."
---

# Quant Signal System

## Workflow

1. Identify the trading universe, horizon, market data granularity, execution assumption, and whether the task is research, backtest, shadow run, or production design.
2. Anchor every signal in a persisted `SignalEvent` with event time, market data time, executable time, executable price, direction, score, confidence, feature snapshot, reason codes, strategy name, and version.
3. Use one strategy path for historical replay and live operation; isolate differences in data source, clock, and execution simulator.
4. Evaluate signals with fixed horizons, MFE, MAE, triple-barrier labels, transaction costs, slippage, delay, and grouped statistics by market regime.
5. Treat backtest-to-live mismatch as a first-class defect. Compare replay output, live shadow output, data boundaries, feature versions, and clock behavior.

## Guardrails

- Do not let future data enter features, labels, standardization, or execution prices.
- Do not optimize parameters on one dataset and present only the best result.
- Do not overwrite historical signals after a strategy change; publish a new version.
- Do not assume a `Sell` signal means shorting in A-share style systems; model it as reduce, clear, stop adding, or risk avoidance unless explicitly specified.
- Do not move to real trading before historical replay, backtest, paper portfolio, and live shadow results are reconciled.

## References

Read `references/quant-signal-system-template.md` for the detailed design and review template. It incorporates the repository's initial short-line quant signal system proposal and should be used for new designs, reviews, or implementation plans.
