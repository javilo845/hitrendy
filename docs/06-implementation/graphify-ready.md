---
id: IMPL-GRAPHIFY-001
kind: agent_infrastructure
status: accepted
related: [DOC-INDEX, AGENTS.md, project-manifest.yaml]
---

# Graphify preparation

## Goal

Make the repository understandable through structure, relationships, and explicit decisions instead of requiring an agent to reread every file.

## Repository features added for Graphify

- Stable document IDs in YAML frontmatter.
- Explicit `related` and `depends_on` links.
- One documentation index.
- Machine-readable `project-manifest.yaml`.
- Mermaid architecture and flow diagrams.
- ADRs for durable decisions.
- JSON schemas for domain contracts.
- Prompt files linked to skill IDs.
- Descriptive filenames instead of generic notes.
- Figma screenshots copied into a named reference folder.

## Suggested run

```bash
uv tool install graphifyy
```

From a supported AI coding assistant, run:

```text
/graphify .
```

Graphify is expected to create a `graphify-out/` directory containing a report and graph data. Do not commit large generated outputs until the team decides whether they are useful in version control.

## Agent orientation sequence

1. Read `graphify-out/GRAPH_REPORT.md` when present.
2. Read `docs/INDEX.md`.
3. Query paths from requirement to screen, API, service, schema, and test.
4. Use raw search only for the remaining implementation detail.

## Useful queries

- Which files implement `FLOW-GEN-001`?
- What depends on `GeneratedSocialPost`?
- Show the path from `ConversationComposer` to `ContentModelProvider`.
- Which ADRs constrain asset uploads?
- Which screens use `BrandProfile`?
- What tests cover workspace authorization?

## Maintenance

Re-run Graphify after:

- new bounded context,
- major route restructure,
- provider interface change,
- schema version change,
- large documentation update.

Documentation changes are part of implementation, not an afterthought.
