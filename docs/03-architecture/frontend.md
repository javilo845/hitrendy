---
id: ARCH-FRONTEND-001
kind: architecture_spec
status: accepted
related: [UX-SCREENS-001, UX-COMPONENTS-001, BRAND-TOKENS-001]
---

# Frontend architecture

## Stack

- Next.js App Router.
- TypeScript with strict mode.
- Tailwind CSS and semantic CSS variables.
- shadcn/ui-compatible component ownership.
- React Hook Form or native React form actions with schema validation.
- Zod for client contract validation.
- TanStack Query only where server-state caching adds value.

## Principles

- Server components by default.
- Client components only for interaction, local state, browser APIs, or streaming.
- Domain-specific components wrap generic UI components.
- API response types are generated or mirrored from the JSON schemas.
- No provider-specific logic in the browser.

## Suggested layout

```text
apps/web/
├── app/
│   ├── (marketing)/
│   ├── (auth)/
│   └── (app)/
│       ├── home/
│       ├── assistant/
│       ├── conversations/
│       ├── templates/
│       ├── projects/
│       ├── library/
│       └── settings/
├── components/
│   ├── ui/
│   ├── shell/
│   ├── assistant/
│   ├── projects/
│   └── templates/
├── features/
├── lib/
├── types/
└── tests/
```

## State ownership

- URL: active route, filters, selected tabs.
- Server: business profile, projects, conversations, artifacts.
- Local component state: form draft, open/closed state, temporary selection.
- Composer draft: local persistence keyed by conversation.

## Streaming

MVP may use a normal request-response cycle. When streaming is enabled:

- Use Server-Sent Events for generation progress.
- Stream status phases or completed sections, not raw internal reasoning.
- Persist final validated artifact before emitting completion.

## Error boundaries

Provide boundaries for:

- authenticated shell,
- assistant thread,
- project editor,
- template catalog.

The user should retain navigation and unsent draft when a child route fails.

## Brand implementation

The supplied Figma uses dark branded surfaces and light content areas. Implement this through `AppShell`, not page-level duplicated gradients. All colors come from `design/tokens.css`.
