# WAVE-011 — Generación de imágenes

## Objetivo

Habilitar imágenes solo cuando una ruta pagada o gratuita real esté disponible y presupuestada.

## Contexto del repositorio


Texto ya debe estar cerrado. Storage y usage ya existen.


## Alcance


- OpenRouter image adapter;
- jobs;
- ratios 1:1,4:5,9:16;
- references;
- storage;
- cost;
- visual brief fallback.


## Inspección obligatoria

Antes de editar:


- capabilities;
- jobs;
- storage;
- artifacts;
- create UI.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Descubrir modelos output=image.
2. Aprobar routes.
3. Preflight cost.
4. Job.
5. persist asset.
6. signed URL.
7. fallback brief.
8. retry/idempotency.


## Contratos


No considerar imagen completa hasta archivo almacenado.


## Pruebas obligatorias


- paid disabled;
- 402;
- success;
- storage failure;
- retry;
- duplicate;
- ratios.


## Criterios de aceptación


- [ ] Cost protected.
- [ ] Files private.
- [ ] Fallback.
- [ ] Usage.
- [ ] CI.


## Prohibiciones


- No base64 gigante en DB.
- No key frontend.
- No llamar paid sin budget.


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
