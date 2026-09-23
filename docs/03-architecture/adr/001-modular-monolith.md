---
id: ADR-001
kind: architecture_decision
status: accepted
---

# ADR-001: Use a modular monolith for MVP

## Context

The team needs a production-shaped but manageable web application for a fair and later improvement.

## Decision

Use one FastAPI deployment with bounded modules and one Next.js web deployment. Keep provider and repository interfaces so modules can be extracted later.

## Consequences

- Simpler local development and deployment.
- Easier transactions and debugging.
- Requires discipline to preserve module boundaries.
- No premature distributed-system complexity.
