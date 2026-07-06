# Enterprise Design Document Template

## 1. Title And Status

- Title:
- Author:
- Reviewers:
- Status: Draft / In review / Approved / Deprecated
- Last updated:
- Target milestone:

## 2. Executive Summary

State the problem, proposed solution, expected impact, and decision needed in one short section.

## 3. Background

Include:

- Current state
- User or business problem
- Relevant system context
- Existing constraints
- Prior decisions
- Related documents or code paths

## 4. Goals

List measurable outcomes:

- Functional goals
- Reliability goals
- Performance goals
- Operability goals
- Security, privacy, or compliance goals
- Delivery goals

## 5. Non-Goals

Name what this design intentionally does not solve. Include tempting future scope to prevent accidental expansion.

## 6. Requirements

### Functional Requirements

- Requirement:
- Source:
- Priority:
- Acceptance criteria:

### Non-Functional Requirements

- Latency:
- Throughput:
- Availability:
- Data durability:
- Observability:
- Backward compatibility:
- Cost:
- Security:

## 7. Proposed Design

### Overview

Describe the design at a high level.

### Components

For each component:

- Responsibility:
- Inputs:
- Outputs:
- Dependencies:
- Owned data:
- Failure behavior:

### Data Flow

```text
Input
  -> validation
  -> processing
  -> persistence
  -> serving / evaluation
```

### APIs And Contracts

Document request/response shapes, event schemas, table schemas, idempotency keys, versioning, and error handling.

### State And Persistence

Explain source of truth, derived data, lifecycle, retention, migrations, and backfills.

### Concurrency And Ordering

State assumptions around ordering, locking, race conditions, duplicate events, retries, and idempotency.

## 8. Alternatives Considered

For each alternative:

- Summary:
- Benefits:
- Drawbacks:
- Why not chosen:

Include the simplest viable alternative and the more scalable alternative when relevant.

## 9. Operational Design

- Deployment plan:
- Configuration:
- Monitoring:
- Alerts:
- Dashboards:
- Runbooks:
- Backfill or replay:
- Incident response:

## 10. Security And Compliance

- Sensitive data:
- Access control:
- Audit trail:
- Data retention:
- Abuse cases:
- Dependency or supply-chain concerns:

## 11. Rollout Plan

Include:

- Feature flags or staged rollout
- Migration sequence
- Backward compatibility
- Rollback plan
- Data verification steps
- Success metrics

## 12. Test And Validation Plan

Cover:

- Unit tests
- Integration tests
- Contract tests
- Replay or migration validation
- Load and latency tests
- Failure injection
- Manual review or signoff

## 13. Risks And Mitigations

| Risk | Impact | Likelihood | Mitigation | Owner |
| --- | --- | --- | --- | --- |

## 14. Open Questions

List unresolved decisions with owners and due dates.

## 15. Implementation Plan

Break work into reviewable milestones:

1. Foundation:
2. Core implementation:
3. Observability and tests:
4. Migration or rollout:
5. Cleanup:

## 16. Review Checklist

- Problem and goals are clear.
- Non-goals prevent scope drift.
- Interfaces and data ownership are explicit.
- Failure modes and recovery are covered.
- Rollout and rollback are realistic.
- Tests validate both correctness and operability.
- Open questions are not hidden as assumptions.
