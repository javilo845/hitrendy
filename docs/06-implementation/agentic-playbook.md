---
id: IMPL-PLAYBOOK-001
kind: implementation_plan
status: accepted
related: [AGENTS.md, DOC-INDEX]
---

# Agentic implementation playbook

This file is the operational plan for another coding model.

## Global protocol

Before each milestone:

1. Read `AGENTS.md` (once per session; skip if already read).
2. Read `docs/INDEX.md` (once per session; skip if already read).
3. Read only specs, schemas, and ADRs relevant to this milestone — do not re-read files unchanged since last session.
4. Query Graphify only if `graphify-out/graph.json` exists OR the repo has >500 files; otherwise grep directly (cheaper).
5. Produce a short implementation plan with files, tests, and estimated rounds.
6. Implement only the milestone scope.
7. Run all checks.
8. Update docs and ADRs only if this milestone actually changed the behavior or architecture they describe.
9. End with a session summary (see below).

## Cost guard

If a milestone exceeds 10 agent rounds without completing, stop and report:
- what was done,
- what blocked completion,
- estimated tokens consumed,
- recommendation: continue, split, or reassess.

This is a hard pause — do not silently continue.

## Session summary

After each completed milestone, produce a 5-10 line summary:
- milestone completed
- files created/modified (count)
- tests added/passed
- tokens consumed (estimated: input ≈ rounds × avg_read, output ≈ rounds × avg_write)
- pending items for next milestone
- docs or ADRs that need updates (if any)

## Milestone 0 — Repository foundation

Atomic checkpoints — stop after each, report, proceed only on go.

### Checkpoint 0a — Project scaffolding
- Initialize monorepo (workspace config, root scripts).
- Place Next.js web app and FastAPI API in their directories.
- Shared contracts location (`contracts/`).
- Verify `npm/pip install` and dev server start individually.

### Checkpoint 0b — Quality and CI
- Formatting (Prettier/ruff), linting (ESLint), type checking (tsc/pyright).
- Test runner config (Vitest + pytest).
- CI config that can run without provider credentials.
- Environment validation (env vars, Docker check).

### Checkpoint 0c — Docker and environment
- `docker-compose.yml` for dev dependencies (DB, cache).
- Dockerfile for each app.
- One-command start (`make dev` or equivalent).

### Checkpoint 0d — Barebones endpoints
- `/health` endpoint in FastAPI.
- Branded shell route in Next.js (renders tokens).
- Full integration: `make dev` → web shows shell → API responds /health.

### Acceptance

- One command starts web and API locally.
- CI can run without provider credentials.
- Brand tokens render in a basic shell.

## Milestone 1 — Business onboarding

### Backend

- Business and brand entities.
- Create/read/update endpoints.
- Database migration.
- Workspace ownership checks.

### Frontend

- Five-step onboarding.
- Autosave or explicit per-step save.
- Review screen.
- Redirect to home.

### Tests

- Required-field validation.
- Resume partial onboarding.
- Cross-workspace access rejection.
- Keyboard navigation through steps.

## Milestone 2 — Assistant vertical slice

### Backend

- Conversation and message entities.
- Intent resolution.
- Demo provider.
- `GeneratedSocialPost` validation.
- Artifact persistence.

### Frontend

- Thread route.
- Message list.
- Composer.
- Structured result card.
- Copy and edit behavior.

### Acceptance

A configured business receives a personalized Instagram post from a free-text request without external credentials.

## Milestone 3 — Variations and projects

- Create linked artifact versions.
- Save as project.
- Recent projects on Home.
- Project editor with save state.
- Prevent regeneration from overwriting user edits.

## Milestone 4 — Templates

- Seed template catalog.
- Search and filters.
- Recommendation skill.
- Create project from selected template.
- Local demo thumbnails.

## Milestone 5 — Asset library and feedback

- Secure upload session.
- Image validation.
- Library listing.
- Demo visual evaluator.
- Real vision provider behind adapter.
- Structured visual review card.

## Milestone 6 — Production AI provider

- Configure provider interface.
- Timeouts, retries, circuit breaker.
- Prompt registry.
- Schema repair.
- Evaluation suite.
- Provider metadata and cost logging.

## Milestone 7 — Polish

- Login flow.
- Conversation search.
- Empty/error/loading states.
- Responsive navigation.
- Accessibility audit.
- Demo data reset.
- Deployment configuration.

## Forbidden shortcuts

- Returning raw model text directly to the UI.
- Adding database access to prompts/tools.
- Storing only chat text without structured artifacts.
- Hardcoding one sample business in production services.
- Treating an icon as accessible without a label.
- Claiming a feature is integrated because a button exists.
