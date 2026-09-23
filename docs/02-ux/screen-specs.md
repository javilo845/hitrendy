---
id: UX-SCREENS-001
kind: ux_spec
status: accepted
related: [FR-001, FR-002, FR-004, FR-005, FR-006]
---

# Screen specifications

## `/login`

### Purpose

Authenticate and introduce the product value.

### Required elements

- HiTrendy logo.
- Welcome heading.
- Email and password.
- Password visibility toggle.
- “Recordarme”.
- Forgot-password link.
- Primary login button.
- Optional Google login behind configuration.
- Registration link.
- Promotional illustration area based on the supplied Figma.

### States

Default, submitting, invalid credentials, network error, account disabled, success redirect.

## `/onboarding`

### Structure

Use a five-step form rather than one long validation survey.

1. Business basics.
2. Audience and location.
3. Channels and goals.
4. Brand identity.
5. Review and save.

### Completion behavior

Save each completed step. Allow later editing. Show progress and estimated remaining time.

## `/app/home`

### Header

Logo, active business selector, account menu.

### Hero

- “¿Qué quieres crear hoy?”
- Main composer.
- Four quick actions:
  - Crear publicación.
  - Escribir guion corto.
  - Mejorar un diseño.
  - Explorar plantillas.

### Secondary content

- Recent projects grid.
- Recommended templates carousel.
- Continue last conversation.

## `/app/assistant`

### Layout

- Collapsible sidebar.
- Centered conversation column.
- Sticky composer.
- Optional right context panel on wide screens.

### Message types

- User text.
- User asset.
- Assistant clarification.
- Assistant explanation.
- Generated artifact card.
- Visual review card.
- Template recommendation row.
- System error or retry notice.

### Composer

- Multiline input.
- Attachment button.
- Voice button behind feature flag.
- Send button.
- Current platform/tone chips.

## `/app/conversations`

- Search field.
- Recent and older sections.
- Title, business, last message, updated time.
- Delete/archive menu.
- Empty state with “Iniciar conversación”.

## `/app/templates`

- Search.
- Filters: platform, format, category, objective.
- Responsive card grid.
- Preview modal.
- “Usar plantilla” creates a draft project.

## `/app/projects`

- Grid/list toggle.
- Folder-like visual may be retained from Figma.
- Project thumbnail, title, type, channel, updated time.
- Create, duplicate, archive, delete.

## `/app/projects/:id`

- Editable copy sections.
- Visual/template preview.
- Version history.
- Copy/export.
- Return to source conversation.
- Save status.

## `/app/library`

- Tabs: Imágenes, Videos, Generados.
- Upload dropzone.
- Search and folder filters.
- Asset cards with ownership and usage count.
- Empty state consistent with Figma.

## `/app/settings`

- Tu cuenta.
- Negocio.
- Identidad de marca.
- Preferencias de contenido.
- Privacidad y datos.
- Activity and usage may be a separate route.
