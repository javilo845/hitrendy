---
id: ADR-003
kind: architecture_decision
status: accepted
---

# ADR-003: Treat AI output as an untrusted external contract

## Context

LLM responses can be incomplete, malformed, or inconsistent.

## Decision

Each AI capability returns a documented JSON shape. The backend validates, normalizes, evaluates, and optionally repairs the response before persistence or display.

## Consequences

- UI remains stable across providers.
- Invalid output does not leak directly to users.
- Adds schema and repair logic.
- Enables deterministic evaluation and tests.
