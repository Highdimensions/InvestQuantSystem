---
name: architecture-review
description: "Independently review software architecture for module boundaries, dependency direction, data ownership, interface contracts, failure isolation, operational complexity, and unnecessary coupling. Use when the user asks for an architecture review, design critique, boundary review, dependency review, modularity assessment, service decomposition review, or complexity risk assessment. Do not use when the request is only to implement code, write tests, debug a localized bug, or produce a full design document rather than a review."
---

# Architecture Review

## Workflow

1. Build a neutral map of modules, dependencies, data stores, ownership boundaries, runtime flows, and external systems.
2. Review dependency direction, interface contracts, data ownership, failure containment, observability, operational burden, and evolution paths.
3. Prioritize findings by blast radius and reversibility. Distinguish architectural risk from local code style preference.
4. Recommend the smallest structural changes that improve isolation, testability, ownership, and future change safety.

## Review Posture

- Prefer evidence from repository structure, code references, schemas, queues, APIs, configs, tests, and deployment topology.
- Treat cycles, hidden shared state, duplicated business rules, cross-layer imports, and ambiguous data authority as high-signal risks.
- Preserve useful simplicity. Do not recommend service splits, event buses, or abstractions unless they solve a concrete pressure.
- Identify where failure should stop, where retries belong, and which component owns recovery.

## References

Read `references/architecture-review-template.md` before producing an architecture review report or checklist.
