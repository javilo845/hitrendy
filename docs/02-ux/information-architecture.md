---
id: UX-IA-001
kind: ux_spec
status: accepted
related: [UX-FIGMA-001]
---

# Information architecture

## Public area

```text
/
├── product explanation
├── examples
├── how it works
├── about HiTrendy
└── login / register CTA
```

## Authenticated application

```text
/app
├── home
├── assistant
│   └── thread/:threadId
├── conversations
├── templates
│   └── template/:templateId
├── projects
│   └── project/:projectId
├── library
│   ├── images
│   ├── videos
│   └── generated
├── activity
└── settings
    ├── account
    ├── business
    ├── brand
    ├── preferences
    └── privacy
```

## Primary navigation

1. Inicio.
2. Asistente.
3. Conversaciones.
4. Plantillas.
5. Proyectos.
6. Biblioteca.
7. Actividad.
8. Configuración.

On narrow screens, use a bottom navigation for Inicio, Asistente, Plantillas, Proyectos, and “Más”.

## Home information priority

1. Primary action: start or continue creation.
2. Context: active business and objective.
3. Suggested creation actions.
4. Recent projects.
5. Recommended templates.
6. Profile completion or account notices.

## Assistant information priority

1. Thread title and active business.
2. Conversation.
3. Structured result cards.
4. Composer with attachment and voice controls.
5. Context controls: platform, objective, tone.

## Project information priority

1. Editable final content.
2. Version selector.
3. Template or asset preview.
4. Export and copy actions.
5. Source conversation and assumptions.

## Entity language

- Conversation: sequence of messages.
- Artifact: structured generated result.
- Project: saved working container with one or more artifact versions.
- Asset: uploaded or generated media file.
- Template: reusable visual/content structure.
- Brand profile: rules and identity applied to generation.
