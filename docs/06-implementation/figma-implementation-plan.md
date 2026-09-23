---
id: IMPL-FIGMA-001
kind: implementation_plan
status: ready_for_execution
related: [UX-FIGMA-001, IMPL-PLAYBOOK-001, E8-T1]
source_of_truth: references/figma/README.md
---

# Figma implementation plan

## Purpose and boundary

This is the execution plan for bringing the frontend into alignment with the
live Figma design. Figma provides visual and component context; the accepted
product, UX, API, and accessibility documents remain the source of behavioral
truth. Do not add features merely because a visual mockup suggests them.

The plan applies after the functional frontend routes exist. It does not change
backend contracts, provider behavior, or the MVP boundary.

## Required tooling gate

Before editing a visual batch, verify all of the following:

1. The Figma plugin is connected in Codex and the agent can read the supplied
   file or node URL.
2. Playwright MCP is available and the local application can be opened.
3. The agent has read the applicable files in `docs/01-brand/` and
   `docs/02-ux/`, plus the relevant route and component code.

If Figma is unavailable, stop visual implementation and report that limitation;
do not reconstruct the system from memory or substitute arbitrary imagery.

## Invariants

- Use semantic design tokens; never hardcode brand colors in components.
- Preserve the existing public API and accessible labels.
- Keep all user-visible product text in Spanish.
- Every batch must cover loading, empty, error, and success states where the
  route owns those states.
- Do not claim pixel-perfect parity without a Figma-context inspection and a
  Playwright comparison.

## Delivery sequence

### Phase 0 — design inventory

- Open the whole Figma file, identify the component library, variables,
  typography, breakpoints, and intended route/frame mapping.
- Record unresolved visual ambiguities in the task summary instead of guessing.
- Map every selected frame to an existing route in
  `docs/02-ux/figma-audit.md`; new routes require a product decision first.

### Phase 1 — shared system and shell

Implement or correct the foundations before individual pages:

- semantic color, typography, spacing, radius, elevation, and breakpoint tokens;
- authenticated and public shells, navigation, focus states, and responsive
  behavior;
- reusable primitives for cards, fields, buttons, dialogs, empty states, and
  status feedback.

Validate the shell at desktop and narrow viewport widths before continuing.

### Phase 2 — entry and core-content batch

Implement the related, highest-value surfaces together:

1. `/login` and `/onboarding`;
2. `/assistant` and its structured result cards;
3. `/projects` and the project editor.

Use the same tokens and primitives from Phase 1. Do not create a one-off visual
language for any page in this batch.

### Phase 3 — creation-support batch

Continue with the supporting content workflow:

1. `/templates` and starting a project from a template;
2. `/library` and visual-feedback states;
3. `/conversations` and `/settings`.

Where Figma lacks a state, use `docs/02-ux/states-and-copy.md` rather than
inventing silent or decorative placeholders.

### Phase 4 — public and remaining surfaces

Finish `/` and any remaining documented route or state. Marketing visuals must
not leak into the authenticated workspace shell. Reuse the established system
unless Figma explicitly defines a separate public-marketing treatment.

### Phase 5 — evidence-based review

For each route batch:

1. Use Playwright to open the running application and complete the critical
   interaction.
2. Capture desktop and mobile states, including one non-happy-path state.
3. Compare hierarchy, spacing, typography, color, responsive behavior, and
   visible component structure against the corresponding Figma node.
4. Fix material discrepancies and rerun the relevant tests.

The final handoff must list the Figma URLs/nodes inspected, Playwright flows
executed, outstanding intentional deviations, and test results.

## Completion criteria

A batch is complete only when its routes preserve behavior, meet the accessible
keyboard and labeling baseline, pass relevant automated tests, and have visual
comparison evidence. Update `docs/06-implementation/backlog.md` only after
those conditions are met.
