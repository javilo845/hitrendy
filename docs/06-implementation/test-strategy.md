---
id: IMPL-TEST-001
kind: quality_spec
status: accepted
---

# Test strategy

## Test pyramid

### Unit tests

- Intent rules.
- Prompt assembly.
- Schema normalization.
- Quality evaluators.
- Authorization policies.
- Template filtering.
- Brand-context resolution.

### Integration tests

- API plus database.
- Migration up/down where practical.
- Provider adapters with recorded fixtures.
- Object storage boundary.
- Idempotency. **Implementado para generación conversacional:** una misma clave
  devuelve el resultado persistido sin crear otro artefacto.

### Contract tests

- Every JSON schema has valid and invalid fixtures.
- Frontend types align with contracts.
- Demo and production providers map to the same artifact type.

### End-to-end tests

1. Register/login.
2. Complete onboarding.
3. Generate post.
4. Create variation.
5. Save project.
6. Reopen project.
7. Upload image and request feedback.

## Quality commands

Recommended root scripts:

```text
lint
format:check
typecheck
test
test:e2e
build
```

## AI regression tests

Run deterministic fixtures on every commit. Run live-provider evaluation only in an explicit protected workflow with cost limits.

## Performance targets for MVP

- Cached simple GET p95 under 500ms in local/staging conditions.
- Conversation page usable under 2.5s on typical broadband.
- Generation request acknowledged under 500ms when queued.
- Provider timeout bounded and visible to user.

## Accessibility tests

- Automated axe checks on main routes.
- Keyboard-only walkthrough.
- Visible focus review.
- Contrast verification for tokens.
- Screen-reader labels for icon controls.

The component test suite runs `vitest-axe` against the assistant conversation
log. Extend this coverage whenever a primary-flow component adds controls or
dynamic status updates; browser walkthroughs remain required for responsive and
focus-order behavior.
