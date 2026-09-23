# WAVE-008C — Post de Instagram en cinco minutos

## Objetivo

Completar el primer flujo de valor de la beta: cuenta configurada → recomendación → post editable y guardado.

## Contexto del repositorio


Negocio, marca, templates, conversaciones y artefactos ya existen.


## Alcance


- home simple;
- CTA crear;
- wizard/post chat;
- output estructurado;
- visual brief;
- edición;
- guardado;
- recuperación.


## Inspección obligatoria

Antes de editar:


- dashboard/home;
- studio workspace;
- templates;
- conversations;
- artifacts/projects;
- prompts.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Seleccionar template Instagram.
2. Precargar contexto.
3. Pedir objetivo/tema.
4. Elegir nivel.
5. Generar recommendation/post.
6. Mostrar caption, CTA, hashtags y visual brief.
7. Editar.
8. Guardar.
9. Duplicar/variar.
10. Instrumentar tiempo hasta valor.


## Contratos


Formato inicial 4:5. No requiere imagen real.


## Pruebas obligatorias


- usuario nuevo E2E;
- contexto de marca;
- forbidden words;
- guardar/recargar;
- idempotencia;
- responsive;
- i18n keys;
- CI.


## Criterios de aceptación


- [ ] Usuario nuevo logra el post.
- [ ] Menos de cinco minutos en prueba manual.
- [ ] Resultado editable.
- [ ] Persistente.
- [ ] Provider real.


## Prohibiciones


- No bloquear por tendencias.
- No prometer imagen.
- No rediseño masivo.


## Entrega del agente

1. Resumen.
2. Arquitectura encontrada.
3. Archivos modificados.
4. Migraciones y datos.
5. Contratos API/UI.
6. Seguridad.
7. Pruebas con resultados exactos.
8. Hallazgos.
9. Limitaciones.
10. Checklist marcado.



No hacer commit ni push. Dejar el working tree revisable.

## Operación del flujo

El flujo vive en `/studio/new` y reutiliza conversaciones, artifacts
versionados y proyectos existentes. Sólo muestra templates Instagram 4:5 del
catálogo aprobado; las cinco URLs de Canva se allowlistean en backend y
frontend. Abrir Canva siempre usa una pestaña nueva con `noopener,noreferrer`.

El resultado contiene caption, CTA, hashtags y un `visual_direction` mostrado
como **visual brief 4:5**. Es una indicación para Canva o un diseñador, no una
imagen generada. El frontend consulta `copywriter.quality_levels` en Capability
Registry, por lo que no anuncia rutas balanced/quality no configuradas ni envía
un ID de modelo.

La edición crea una versión de artifact sólo al guardar y conserva los cambios
locales si falla el guardado. El proyecto conserva `source_template_id`, el
artifact, plataforma y su formato. Duplicar usa la misma relación padre de
versiones; variar reutiliza el endpoint versionado de artifacts.

La creación y el duplicado aceptan `Idempotency-Key`: un replay devuelve el
mismo proyecto y un artifact ya asociado no se reasigna. Al guardar, el studio
reemplaza la URL por `/studio/new?project=<id>` y reconstruye el resultado desde
el proyecto y su última versión; las ediciones pendientes activan protección de
salida.

## Tiempo hasta valor y prueba manual

`creation_flow_events` guarda solamente `workspace_id`, `business_id`,
`flow_started_at`, `first_generation_completed_at`, `elapsed_seconds` y
`completion_status`; no guarda tema, prompts ni contenido. Para la prueba
manual: inicia sesión con una cuenta configurada, abre **Crear con HiTrendy**,
selecciona un template, escribe un tema, genera, revisa el visual brief y
guarda. Compara los timestamps del evento para verificar que termina en menos
de cinco minutos. El E2E reproduce el recorrido completo con provider fake;
el smoke real sigue siendo opt-in y requiere credenciales OpenRouter.
