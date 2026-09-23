# AGENTS.md — Rules for Coding Agents

## Mission

Implement HiTrendy as a maintainable web product: a personalized AI assistant that helps small businesses create and improve social-media content.

## Reading before editing

Read these once per session (skip if already read in same session):

1. `docs/INDEX.md`
2. `docs/00-product/vision-and-scope.md`

Then read only what is relevant to the current milestone:
3. The relevant feature specification
4. Relevant JSON schemas in `contracts/schemas/`
5. Relevant ADRs
6. `docs/03-architecture/system-context.md` (only if working on architecture)
7. `docs/03-architecture/backend.md` or `frontend.md` (only if changing that layer)

Do not re-read files unchanged since the last session.

## Token guard — never read these

- `.venv/` — project virtualenv (122 MB, ~thousands of files). Never read or traverse.
- `.env/` — demo virtualenv. Never read or traverse.
- `**/__pycache__/` — compiled bytecode, zero signal.
- `**/.pytest_cache/` — test runner cache, zero signal.

Do not scan, grep, or glob inside these directories. They contain no source code or configuration.

## Model routing

- Use a fast/cheap model for: file search, globbing, grep, reading known files, formatting, lint fixes.
- Use a capable reasoning model for: architecture decisions, generating implementations, writing tests, debugging complex errors.
- Use a vision model only when you need to read a screenshot or Figma export in `references/figma/`.

## Hard constraints

- Do not expand the MVP into a trend-monitoring platform.
- Do not train an LLM during normal request handling.
- Do not let the LLM query the database directly.
- Do not hardcode brand colors in components; use semantic tokens.
- Do not claim a social-network integration is available unless it is implemented and authorized.
- Do not store raw secrets, passwords, or provider keys in source control.
- Do not publish generated content automatically in MVP.
- Every generated artifact must remain editable by the user.
- Every provider must be replaceable through an interface.
- Demo mode must remain runnable without external credentials.

## Implementation method

For every task:

1. Identify the owning domain and linked requirement IDs.
2. State the files that will change.
3. Preserve public contracts unless the task explicitly changes them.
4. Add or update tests before declaring completion.
5. Run formatting, type checks, unit tests, and integration tests.
6. Update documentation only when behavior or architecture actually changed.
7. Add an ADR only for a durable architectural decision (not for routine implementation).

## Definition of done

A task is done only when:

- Acceptance criteria pass.
- Error, loading, empty, and success states are represented.
- Authorization boundaries are tested.
- Structured outputs validate against schemas.
- No provider-specific object leaks into the domain layer.
- User-visible text is in Spanish unless it is a technical identifier.
- Accessibility basics are preserved: keyboard, labels, focus, contrast.
- Documentation links remain valid.

## Preferred vertical slices

Implement end-to-end behavior in this order:

1. Business onboarding.
2. Text-content generation.
3. Project persistence.
4. Template recommendation.
5. Asset upload and visual feedback.
6. Conversation history.
7. Voice input.
8. Optional trend context.

Avoid building all database models before a usable slice exists.

## Graphify workflow

After meaningful structure exists:

```bash
uv tool install graphifyy
# Then from a supported coding assistant:
/graphify .
```

Before broad code search, inspect:

- `graphify-out/GRAPH_REPORT.md`
- `docs/INDEX.md`
- `project-manifest.yaml`

Use `/graphify query`, `/graphify path`, or `/graphify explain` for dependency questions before grepping the full repository.

Use raw grep/glob instead of Graphify when the repository has fewer than 500 files — Graphify overhead exceeds its value at that scale.

@RTK.md
