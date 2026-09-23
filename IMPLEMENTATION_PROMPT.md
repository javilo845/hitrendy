# Ready-to-use implementation prompt

Use this prompt with a coding agent after placing this package at the root of the repository.

---

You are implementing HiTrendy, a web assistant that helps small businesses create and improve social-media content. Treat this repository as contract-first and documentation-led.

Before changing code:

1. Read `AGENTS.md`.
2. Read `docs/INDEX.md`.
3. Read `docs/00-product/vision-and-scope.md`.
4. Read `docs/03-architecture/system-context.md`.
5. Read `docs/06-implementation/agentic-playbook.md`.
6. Inspect `contracts/schemas/` and the relevant ADRs.
7. If `graphify-out/GRAPH_REPORT.md` exists, read it and use Graphify queries before broad repository search.

Implement only the next incomplete milestone from the agentic playbook. Begin by reporting:

- the milestone,
- linked requirement IDs,
- files to create or modify,
- migrations and contract impact,
- tests to add,
- assumptions or blockers.

Then implement the smallest complete vertical slice. Do not add unrelated features. Preserve the HiTrendy brand tokens. Keep AI providers interchangeable. Never return unvalidated model output directly to the browser. Demo mode must remain functional without external credentials.

Before finishing, run formatting, linting, type checks, unit tests, integration tests, and the relevant end-to-end path. Update documentation and ADRs when behavior or architecture changes. Report exactly what passed, what remains, and any known limitation.

---
