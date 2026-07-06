---
name: test-and-evaluation-plan
description: "Design test and evaluation plans for systems that need unit correctness, data replay, backtest correctness, live-vs-replay consistency, delayed evaluation, latency behavior, and failure recovery validation. Use when the user asks for a test plan, evaluation plan, QA strategy, replay validation, backtest validation, realtime consistency checks, or resilience tests. Do not use for merely running an existing test command, fixing a single failing unit test, or writing unrelated product acceptance criteria without technical evaluation depth."
---

# Test And Evaluation Plan

## Workflow

1. Identify correctness surfaces: pure functions, stateful components, data boundaries, clocks, persistence, backtest engine, live shadow path, and recovery behavior.
2. Define deterministic fixtures and golden cases before broad stochastic or historical tests.
3. Cover replay/live consistency with the same inputs, same strategy version, same feature version, and explicit clock semantics.
4. Validate failure recovery by interrupting ingestion, evaluation, persistence, and workers, then proving idempotent resume.
5. Report test scope, fixtures, assertions, metrics, pass criteria, and remaining risks.

## Test Design Principles

- Test time and price semantics directly; many quant bugs hide in boundary conditions.
- Prefer invariant checks and golden replays for backtest correctness.
- Include negative tests for missing bars, duplicate ticks, delayed data, halted symbols, and partial writes.
- Separate signal quality evaluation from system correctness evaluation.
- Make tests reproducible: pin data snapshots, strategy versions, parameters, time zones, and costs.

## References

Read `references/test-and-evaluation-plan-template.md` when drafting a test plan, evaluation strategy, or validation checklist.
