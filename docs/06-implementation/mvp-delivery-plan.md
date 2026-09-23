---
id: IMPL-MVP-DELIVERY-001
kind: implementation-plan
status: proposed
owner: product-engineering
updated: 2026-07-23
---

# Plan de entrega del MVP

## Decisión de alcance

El frontend y el backend ya tienen una base funcional y pruebas automatizadas,
pero el MVP no se declara operativo hasta comprobar el recorrido completo con
un proveedor configurado y persistencia real.

La primera fase excluye únicamente el análisis de tendencias en tiempo real.
Todo lo necesario para crear, revisar, editar y guardar contenido sí pertenece
al MVP.

## Fase 1 — MVP funcional mínimo

### 1.1 Entorno y proveedor de IA

- Configurar `AI_PROVIDER=openai-compatible`.
- Configurar OpenRouter mediante `AI_BASE_URL`, `AI_API_KEY` y `AI_MODEL`.
- Mantener el proveedor demo como fallback local y para pruebas sin credenciales.
- Verificar que las respuestas cumplen los schemas de publicación y guion.
- Añadir límites de tiempo, errores visibles y reintento seguro.

**Aceptación:** una solicitud real genera un resultado estructurado sin que la
clave de API llegue al navegador.

### 1.2 Identidad y negocio

- Registro e inicio de sesión con cookie HttpOnly.
- Logout que invalida sesión y protege de nuevo las rutas privadas.
- Onboarding del negocio.
- Perfil de marca usado en cada generación.

**Aceptación:** un usuario nuevo puede completar onboarding y llegar a Studio;
un usuario sin sesión no puede leer datos privados.

### 1.3 Publicaciones y guiones

- Crear conversación desde Studio.
- Generar publicación social con `create_social_post`.
- Generar guion corto con `create_short_video_script`.
- Mostrar el resultado estructurado y sus supuestos.
- Pedir variaciones.
- Editar el contenido antes de guardarlo.

**Aceptación:** el usuario obtiene una publicación y un guion editables en menos
de cinco minutos, usando el contexto de su negocio.

### 1.4 Proyectos, plantillas y assets

- Guardar artefactos como proyectos versionados.
- Editar, duplicar, archivar, restaurar y exportar proyectos.
- Iniciar un proyecto desde una plantilla y abrir su editor.
- Buscar y filtrar plantillas con miniaturas locales válidas.
- Subir un asset con validación de tipo, tamaño y dimensiones.
- Consultar la biblioteca de assets.

**Aceptación:** después de recargar Dashboard, el proyecto y su última versión
siguen disponibles.

### 1.5 Análisis visual

- Mantener `VISION_PROVIDER=demo` para la primera entrega.
- Permitir subir una imagen desde Studio.
- Devolver fortalezas, mejoras, CTA, legibilidad y accesibilidad.
- Mantener el adaptador compatible con un proveedor multimodal posterior.

**Aceptación:** una imagen autorizada produce una revisión estructurada sin
exponer el archivo mediante una URL pública.

### 1.6 Cierre de Fase 1

- Typecheck, lint, pruebas unitarias y build.
- Pruebas backend completas.
- E2E con servidor aislado y recorrido Home → Login/demo → Studio → Dashboard.
- Smoke manual contra backend real y OpenRouter configurado.
- Documentar variables de entorno, límites gratuitos y pasos de demo.

**Criterio de salida:** la aplicación puede crear y guardar contenido real. No
se presenta como plataforma de tendencias.

## Fase 2 — Pulido y expansión

### 2.1 Calidad de producto

- Revisión visual final contra Figma.
- Auditoría manual de foco, contraste y `prefers-reduced-motion`.
- Mejorar estados de carga, vacío, error y recuperación.
- Reducir warnings de CSS y dependencias.

### 2.2 Operación y escala

- Idempotency keys en mutaciones y generaciones.
- Búsqueda, paginación y carga incremental de plantillas desde servidor.
- Observabilidad de latencia, errores y uso sin guardar contenido sensible.
- Límites y fallback entre proveedores.
- Separar almacenamiento demo de persistencia de producción.

### 2.3 Contexto de tendencias — opcional

- Diseñar un contrato `trend_context` independiente.
- Usar fuentes públicas, autorizadas y trazables.
- Mostrar fecha, fuente y nivel de confianza.
- No convertir tendencias en un dashboard de escucha social.

Esta subfase no bloquea la Fase 1 y no debe simular datos si no existe una
fuente conectada.

## Checklist de entrega

- [ ] OpenRouter configurado y probado desde backend.
- [ ] Registro, login, logout y onboarding reales.
- [ ] Publicación social generada y editable.
- [ ] Guion corto generado y editable.
- [ ] Proyecto guardado y visible tras recarga.
- [ ] Plantilla crea proyecto persistente.
- [ ] Asset subido y análisis visual ejecutado.
- [ ] Demo offline sigue funcionando sin claves externas.
- [x] Frontend: typecheck, lint, unit tests y build.
- [x] Backend: suite automatizada.
- [x] E2E frontend: desktop y móvil con API simulada.
- [ ] Smoke E2E con backend y proveedor real.
- [ ] Análisis de tendencias: explícitamente fuera de Fase 1.

## Qué significa “MVP completo”

El MVP estará completo cuando todos los puntos de la Fase 1 estén verificados
contra el backend real. Las pruebas con API simulada demuestran el flujo de UI,
pero no sustituyen la validación de credenciales, límites, respuestas del
proveedor ni persistencia de producción.
