---
id: ADR-002
kind: architecture_decision
status: accepted
---

# ADR-002: Use a pretrained model with runtime context

## Context

HiTrendy needs language capability and business personalization. Training a model for each customer or each request would be expensive, slow, and unsafe.

## Decision

Use an existing pretrained LLM. Supply current business, brand, request, and optional template context at runtime. Validate structured outputs. Fine-tuning is not required for MVP.

## Consequences

- Faster implementation.
- Current data can be updated without retraining.
- Prompt and evaluation quality become important.
- Provider can be local or cloud-based.
