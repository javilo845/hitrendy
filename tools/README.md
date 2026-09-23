# Frontend design tools

This repository uses the following audited frontend resources:

- `pbakaus/impeccable` → `.agents/skills/impeccable`
- `nextlevelbuilder/ui-ux-pro-max-skill` → `.agents/skills/{design,design-system,ui-styling,...}`
- `emilkowalski/skills` → `.agents/skills/{emil-design-eng,review-animations,...}`
- `juliangarnier/anime` → `animejs` in `starter/web/package.json`
- `animate-css/animate.css` → `animate.css` in `starter/web/package.json`

## Screenshot-to-code

The standalone `abi/screenshot-to-code` application is vendored under
`tools/screenshot-to-code/` for isolated use. It requires its own backend,
provider API keys, and browser/runtime dependencies; it is not part of the
HiTrendy runtime or workspace scripts. Its remote installer was intentionally
not copied or executed.

<https://github.com/abi/screenshot-to-code>

## Provenance

The skills were copied from shallow clones on 2026-08-02. The exact source
commits are recorded in `docs/06-implementation/frontend-tools.md`.
