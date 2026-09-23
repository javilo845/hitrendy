---
id: BRAND-TOKENS-001
kind: design_spec
status: accepted
related: [BRAND-SYSTEM-001]
---

# Design tokens

## Principle

Components consume semantic tokens. Raw palette values are defined once and never scattered through component files.

## Semantic roles

```text
--background
--foreground
--surface
--surface-elevated
--card
--card-foreground
--primary
--primary-hover
--primary-foreground
--secondary
--secondary-foreground
--muted
--muted-foreground
--border
--input
--focus
--success
--warning
--danger
```

## Dark application shell

The navigation and creative workspace may use the dark palette while forms, onboarding, and content editors use light surfaces. The application is not a full “dark mode”; it is a mixed branded interface.

## Spacing

Use a 4px base grid:

| Token | Value |
|---|---:|
| space-1 | 4px |
| space-2 | 8px |
| space-3 | 12px |
| space-4 | 16px |
| space-5 | 20px |
| space-6 | 24px |
| space-8 | 32px |
| space-10 | 40px |
| space-12 | 48px |
| space-16 | 64px |

## Layout

- Desktop content max-width: 1440px.
- Sidebar collapsed: 72px.
- Sidebar expanded: 240px.
- Main content padding: 32px desktop, 20px tablet, 16px mobile.
- Chat reading column: 760px max.
- Marketing landing sections: 1200px max.

## Responsive breakpoints

- Mobile: below 640px.
- Tablet: 640–1023px.
- Desktop: 1024px and above.
- Wide: 1440px and above.

## Motion

- Microinteraction: 120–180ms.
- Panels and dialogs: 180–240ms.
- Use ease-out for entry and ease-in for exit.
- Respect `prefers-reduced-motion`.

## Implementation files

- `design/tokens.css`
- `design/tokens.json`
- `starter/web/app/globals.css`
