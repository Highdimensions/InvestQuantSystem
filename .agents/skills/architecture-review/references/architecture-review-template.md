# Architecture Review Template

## 1. Review Scope

- System or module under review:
- Source artifacts reviewed:
- Business capability supported:
- Runtime shape:
- Deployment shape:
- Out of scope:

## 2. Architecture Map

Describe the system in terms of:

- Modules and packages
- Services, jobs, workers, or command-line entry points
- Data stores, files, queues, and caches
- External dependencies
- Public interfaces
- Main request, event, or batch flows

Use a small diagram when helpful:

```text
Caller
  -> API / command
  -> Application service
  -> Domain logic
  -> Repository / adapter
  -> Storage or external system
```

## 3. Boundary Review

For each major module:

- Responsibility:
- Owned data:
- Public interface:
- Dependencies:
- Who calls it:
- Who it calls:
- State it mutates:
- Failure it may produce:
- Tests that define the boundary:

Look for:

- Business rules split across unrelated layers
- Shared mutable state crossing boundaries
- Modules that both orchestrate and implement low-level details
- Domain logic hidden in adapters, UI, migrations, or scripts
- Interfaces that expose storage internals

## 4. Dependency Direction

Expected direction:

```text
UI / CLI / API
  -> application orchestration
  -> domain logic
  -> ports / interfaces
  -> infrastructure adapters
```

Review questions:

- Are lower-level modules importing higher-level modules?
- Are domain modules importing framework, database, broker, or UI details?
- Are there circular imports or runtime cycles?
- Are test-only helpers leaking into production code?
- Can adapters be replaced without changing domain logic?

## 5. Data Ownership

For every important entity or dataset:

- Source of truth:
- Allowed writers:
- Allowed readers:
- Update path:
- Versioning rules:
- Retention and replay expectations:
- Auditability:
- Backfill behavior:

Common risks:

- Multiple writers for the same fact
- Derived data later treated as source data
- Silent mutation of historical records
- Inconsistent identifiers across modules
- Missing owner for schema evolution

## 6. Interface Contracts

Review each API, event, table, file, or function contract:

- Required fields:
- Optional fields:
- Versioning strategy:
- Idempotency key:
- Error model:
- Retry expectations:
- Ordering guarantee:
- Time zone and clock semantics:
- Compatibility requirements:

Prefer contracts that make invalid states hard to represent.

## 7. Failure Isolation

For each flow, identify:

- What can fail:
- How failure is detected:
- Where failure is contained:
- Retry policy:
- Dead-letter or quarantine path:
- Backpressure behavior:
- Recovery procedure:
- Data consistency after partial failure:

Review whether one failing dependency can corrupt state, block unrelated work, or create unbounded queues.

## 8. Complexity Assessment

Assess:

- Essential complexity from the domain
- Accidental complexity from abstractions, services, queues, configuration, or duplication
- Operational complexity for deployment, monitoring, backfill, and incident response
- Change complexity for adding a feature or replacing a dependency

Name the complexity budget explicitly:

- Keep:
- Simplify:
- Defer:
- Remove:

## 9. Findings Format

Use this format:

```text
[Severity] Finding title
Evidence:
Impact:
Recommendation:
Tradeoff:
```

Severity guide:

- P0: Can corrupt data, cause major outage, or invalidate core system results.
- P1: High likelihood of costly incidents, incorrect behavior, or blocked evolution.
- P2: Meaningful maintainability or operational risk.
- P3: Improvement suggestion with limited immediate risk.

## 10. Final Recommendation

Conclude with:

- Architecture decision: approve, approve with required changes, or redesign before implementation
- Required changes before build or merge
- Follow-up investigations
- Risks accepted by stakeholders
