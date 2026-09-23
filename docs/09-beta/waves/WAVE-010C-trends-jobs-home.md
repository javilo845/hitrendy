# WAVE-010C — Ejecución diaria y Home de tendencias

## Objetivo

Programar análisis diario, refresh manual con cooldown y Home con tarjetas verificables.

## Contexto del repositorio


El usuario eligió tendencias como primera pantalla.


## Alcance


- scheduler;
- regional reuse;
- manual refresh;
- home API/UI;
- create post from trend.


## Inspección obligatoria

Antes de editar:


- job infrastructure;
- trends API;
- dashboard;
- usage.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Job por región/categoría.
2. Lock/idempotencia.
3. Compute business scores.
4. Refresh cooldown.
5. Home states.
6. sources modal.
7. create post CTA.


## Contratos


Diferenciar trend/recommendation.


## Pruebas obligatorias


- daily idempotent;
- concurrent refresh;
- no source;
- stale;
- home;
- CTA.


## Criterios de aceptación


- [ ] Home útil.
- [ ] Daily.
- [ ] Manual.
- [ ] Sources.
- [ ] No duplicados.


## Prohibiciones


- No run completo por usuario.
- No ocultar fechas.


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
