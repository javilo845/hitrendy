# HiTrendy package manifest

## Package summary

- Total files: 104
- Markdown documents: 51
- Python files: 8
- JSON contracts/configuration: 10
- Approximate text/code lines: 4971
- Supplied Figma references: 8 PNG files
- Demo tests: 4 passed
- JSON validation: passed
- Internal Markdown link validation: passed

## Main deliverables

- `README.md`: package entry point.
- `IMPLEMENTATION_PROMPT.md`: ready-to-use coding-agent prompt.
- `AGENTS.md` and `CLAUDE.md`: repository behavior rules.
- `docs/`: product, brand, UX, architecture, AI, API, implementation, and demo specifications.
- `design/`: CSS/JSON tokens and visual brand preview.
- `contracts/`: machine-readable schemas, prompt contracts, and fixtures.
- `demo/`: runnable offline FastAPI + web demo.
- `starter/`: production-oriented Next.js and FastAPI foundations.
- `references/figma/`: the supplied visual references with descriptive names.
- `project-manifest.yaml`: Graphify-friendly project relationships.

## Verification commands

```bash
python scripts/validate_package.py
cd demo && pytest -q
```

## Graphify entry

Read `docs/06-implementation/graphify-ready.md`, install Graphify, and run `/graphify .` from a supported coding assistant.
