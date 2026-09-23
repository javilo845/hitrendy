# WAVE-008A — Registro de capacidades y disponibilidad

## Objetivo

Implementar la capa que sabe qué APIs/modelos están configurados, gratuitos, pagados, agotados o restringidos.

## Contexto del repositorio


La configuración actual tiene un único modelo de contenido y visión.


## Alcance


- estados;
- registry;
- endpoint público;
- admin config;
- health cache;
- error mapping;
- context seguro para IA.


## Inspección obligatoria

Antes de editar:


- config;
- provider factory;
- errors;
- DB models;
- API routes;
- frontend settings/create.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Definir enums.
2. Añadir modelos/migración.
3. Crear registry.
4. Integrar OpenRouter, tendencias, image/video flags.
5. Endpoint sanitizado.
6. UI deshabilitada con explicación.
7. Prompt capability context.
8. Cache con Redis y persistencia de último health.


## Contratos


```text
GET /capabilities
GET /admin/integrations
PATCH /admin/integrations/{key}
```
Admin requiere rol.


## Pruebas obligatorias


- sanitización;
- status transitions;
- free/paid;
- quota;
- UI;
- no secret;
- concurrency;
- E2E.


## Criterios de aceptación


- [ ] La app sabe qué puede hacer.
- [ ] La IA recibe resumen seguro.
- [ ] UI no ofrece funciones falsas.
- [ ] No se expone saldo/secreto.
- [ ] CI pasa.


## Prohibiciones


- No realizar llamadas costosas en cada request.
- No inferir disponibilidad solo por presencia de key.
- No crear admin por URL oculta.


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
