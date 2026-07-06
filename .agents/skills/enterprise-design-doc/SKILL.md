---
name: enterprise-design-doc
description: "Transform scattered requirements, notes, prototypes, or early solution ideas into engineering design documents that can be reviewed and implemented in a large-company environment. Use when the user asks for a design doc, technical proposal, RFC, architecture proposal, implementation plan, requirements-to-design rewrite, or review-ready engineering document. Do not use for pure code implementation, short one-off answers, product marketing copy, simple README writing, or architecture critique without producing a design document."
---

# Enterprise Design Doc

## Workflow

1. Gather the source material: user goals, constraints, existing code or docs, stakeholders, rollout expectations, non-goals, risks, and unresolved decisions.
2. Separate product intent from engineering decisions. Preserve ambiguity as explicit open questions instead of silently inventing requirements.
3. Produce a reviewable document with clear ownership, scope, alternatives, interfaces, rollout, observability, test strategy, and risk controls.
4. Call out decisions that need approval, assumptions that affect design, and follow-up work needed before implementation.

## Required Output Qualities

- Make the document implementable by engineers and reviewable by architecture, security, data, operations, and product stakeholders.
- Prefer concrete contracts, data flows, APIs, schemas, state transitions, failure modes, rollout steps, and validation criteria over generic prose.
- Include non-goals and rejected alternatives to reduce future scope drift.
- Distinguish facts from assumptions and recommendations.
- Keep diagrams text-based unless the user asks for another artifact format.

## References

Read `references/design-doc-template.md` when creating or restructuring a design document. Use its section order unless the repository or user provides a stronger local convention.
