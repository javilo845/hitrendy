---
id: UX-COMPONENTS-001
kind: component_spec
status: accepted
related: [BRAND-TOKENS-001, UX-SCREENS-001]
---

# Component contracts

## `AppShell`

**Responsibility:** consistent authenticated layout.

Inputs:

- currentRoute
- businessSummary
- userSummary
- navItems
- children

Rules:

- Sidebar collapses without losing accessible labels.
- Mobile uses drawer or bottom navigation.
- No route-specific business logic.

## `ConversationComposer`

Inputs:

- value
- attachments
- selectedPlatform
- selectedTone
- isSending
- featureFlags

Events:

- onChange
- onAttach
- onRemoveAttachment
- onSend
- onStartVoice

Rules:

- Enter sends; Shift+Enter inserts line break.
- Prevent duplicate submit.
- Show upload progress.
- Preserve draft per thread.

## `GeneratedArtifactCard`

Inputs:

- artifact
- selectedVersion
- permissions

Actions:

- edit
- copy
- save
- createVariation
- chooseTemplate
- reportIssue

Rendering is based on `artifact_type`, never on provider-specific response shape.

## `VisualReviewCard`

Sections:

- Resumen.
- Lo que funciona.
- Prioridades de mejora.
- Texto revisado.
- Accessibility notes.

Each recommendation contains priority, reason, and proposed action.

## `TemplateCard`

Inputs:

- id
- title
- thumbnailUrl
- formats
- category
- premiumFlag

Do not show unavailable actions. Demo mode uses local thumbnails.

## `ProjectCard`

Inputs:

- title
- thumbnail
- artifactType
- platform
- updatedAt
- status

Actions are in a menu and keyboard-accessible.

## `BusinessContextChip`

Shows the active business and allows switching only when the user has access to multiple businesses.

## `AsyncState`

Unified presentation for:

- loading,
- empty,
- error,
- permission denied,
- rate limited,
- provider unavailable.

No screen should invent its own error pattern.
