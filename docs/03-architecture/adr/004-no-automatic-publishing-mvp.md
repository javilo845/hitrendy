---
id: ADR-004
kind: architecture_decision
status: accepted
---

# ADR-004: Do not automatically publish in MVP

## Decision

HiTrendy generates and organizes editable drafts. The user must review and manually copy/export content.

## Rationale

This avoids platform-auth complexity, accidental publication, policy risk, and a misleading demo. Publishing integrations may be added later with explicit approvals.
