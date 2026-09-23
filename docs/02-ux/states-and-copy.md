---
id: UX-STATES-001
kind: ux_spec
status: accepted
---

# States and interface copy

## Assistant loading

- Initial: “Preparando una propuesta para tu negocio…”
- Tool execution: “Revisando tu perfil de marca…”
- Finalization: “Organizando el contenido para que puedas editarlo.”

Avoid fake precision or claims about external analysis.

## Empty conversation

Heading: “¿Qué quieres crear hoy?”

Suggestions:

- “Una publicación para promocionar un producto.”
- “Un guion corto para Reel o TikTok.”
- “Ideas para anunciar una promoción.”
- “Comentarios sobre un diseño que ya hice.”

## Missing onboarding

“Para personalizar tus resultados necesitamos conocer algunos datos de tu negocio.”

CTA: “Configurar mi negocio”.

## Provider error

“No pudimos generar el contenido en este momento. Tu mensaje está guardado; puedes intentarlo nuevamente.”

Do not expose provider names or stack traces.

## Upload rejection

- Unsupported: “Este tipo de archivo no es compatible. Usa PNG, JPG o WebP.”
- Too large: “El archivo supera el tamaño permitido de 10 MB.”
- Unsafe: “No pudimos procesar este archivo.”

## Save confirmation

“Proyecto guardado.”

Secondary: “Lo encontrarás en Tus proyectos.”

## Delete confirmation

Title: “¿Eliminar este proyecto?”

Body: “Esta acción enviará el proyecto a la papelera. Podrás recuperarlo durante 30 días.”

## AI disclaimer

Display near generated results, not on every message:

“Contenido generado como borrador. Revísalo antes de publicarlo.”
