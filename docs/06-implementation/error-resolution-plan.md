---
id: IMPL-ERROR-PLAN-001
kind: implementation-plan
status: in_progress
owner: frontend
updated: 2026-07-22
---

# Plan de resolución de errores frontend

## Objetivo de la entrega inmediata

Dejar un recorrido demostrable y estable para mañana:

`Home -> Login/demo -> Studio -> generar/guardar contenido -> Dashboard`.

El backend ya dispone de contratos para autenticación, conversaciones,
proyectos, plantillas, assets y revisión visual. No se debe sustituir esa
arquitectura ni inventar una API paralela.

## P0 — bloquear antes de la entrega

### 1. Logout contra API real

`POST /api/v1/auth/logout` responde `204 No Content`, pero el cliente web
intentaba parsear JSON para toda respuesta exitosa. El cliente ahora devuelve
`undefined` en `204`; el App Shell limpia el modo demo y vuelve a Home.

**Aceptación:** login real, logout real y segundo acceso sin sesión no producen
errores de parsing ni dejan datos privados visibles.

### 2. Crear proyecto desde plantilla

La biblioteca web guardaba el ID de plantilla y abría Studio sin persistir
nada. Ahora crea el proyecto editable con `POST /projects`, `template_id` y el
negocio activo, y abre directamente el editor de proyecto. Ese destino muestra
el primer artefacto y sus versiones; el contrato actual no define una
conversación asociada a un proyecto de plantilla, por lo que no se inventó esa
relación.

**Aceptación:** `Usar plantilla` crea un proyecto persistente, muestra su primer
artefacto editable y aparece en Dashboard después de recargar.

### 3. Miniaturas de plantillas seed

El seed backend referencia `/static/thumbnails/*.svg`, mientras que esos paths
no están disponibles en el servidor web integrado. El adaptador de presentación
mapea los IDs seed a assets locales existentes y muestra un fallback accesible
si una imagen falla.

**Aceptación:** cada tarjeta muestra imagen válida en API real, demo y build de
producción, con estado alternativo accesible si falta un asset.

## P1 — completar si queda tiempo

- [x] Smoke E2E estable en Chromium desktop y móvil para Home, login/demo,
      Studio, Dashboard, búsqueda/filtros y Settings. Usa un servidor aislado en
      el puerto 3100 para no reutilizar procesos locales.
- [x] Estados de error visibles en generación, proyectos y plantillas; el modo
      demo conserva el proyecto creado dentro de la sesión del navegador.
- [ ] Verificar visualmente `prefers-reduced-motion`, foco y contraste en rutas
      nuevas como revisión manual de entrega.
- [x] Actualizar la evidencia de assets con la resolución de miniaturas seed.

## P2 — después de la entrega

- Idempotency keys en mutaciones web.
- Búsqueda/paginación de plantillas desde servidor cuando el catálogo crezca.
- Instrumentación adicional de uso sin almacenar contenido sensible.
- Revisión Graphify y comparación visual final con Figma.

## Fuera de alcance para mañana

El roadmap y `AGENTS.md` mantienen el análisis de tendencias en tiempo real fuera
del MVP. No se debe presentar como implementado ni consumir fuentes externas sin
contrato, autorización y pruebas. Primero se entrega la creación y persistencia
de contenido; `trend_context` puede añadirse después como proveedor opcional.

## Checklist de cierre

- [x] P0.1 logout `204` corregido y probado.
- [x] P0.2 plantilla crea proyecto persistente y abre su editor editable.
- [x] P0.3 miniaturas seed sin rutas rotas y con fallback accesible.
- [x] Typecheck, lint, pruebas unitarias y build frontend pasan.
- [x] Suite backend pasa.
- [x] E2E Chromium estable y documentado: 22 pruebas desktop/móvil.
