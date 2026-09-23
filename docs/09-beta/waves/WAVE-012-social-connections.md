# WAVE-012 — Conexiones con redes propias

## Objetivo

Conectar cuentas profesionales autorizadas para métricas propias, sin convertirlo en scraping global.

## Estado de implementación

**Completada — 2026-08-02.** Esta wave entrega la base segura para conectar una cuenta que el usuario ya posee. La implementación está limitada a un proveedor demo offline y a Instagram Login for Business; TikTok y X aparecen como no disponibles hasta contar, respectivamente, con aprobación de plataforma y un plan de API compatible.

La conexión no habilita publicación, programación, scraping, lectura de timelines ni selección de múltiples cuentas. Si un proveedor devuelve más de una cuenta elegible, el callback rechaza el resultado completo.

## Contexto del repositorio


Instagram/TikTok/X tienen permisos y términos diferentes.


## Alcance


- OAuth/token vault;
- Instagram professional;
- X solo si pago;
- TikTok approved APIs;
- import own posts;
- revoke.

**Fuera de alcance:** la selección de múltiples cuentas se difiere; si un proveedor devuelve más de una, se rechaza de forma segura.


## Inspección obligatoria

Antes de editar:


- integrations;
- OAuth;
- storage secrets;
- analytics.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. ADR por plataforma: [ADR-005](../../03-architecture/adr/005-social-connections.md).
2. Tokens cifrados.
3. Scopes mínimos.
4. Revocación local y remota cuando el proveedor la confirma.
5. Estado de conexión comprobable bajo acción del usuario.
6. Estado de disponibilidad por proveedor.
7. Desconexión y purga al eliminar la identidad o el workspace.

La renovación automática y la importación de métricas/publicaciones propias quedan para un slice posterior específico por proveedor; no se simulan en esta entrega.


## Contratos


No usar conexiones sociales como registro principal.


## Pruebas obligatorias


- OAuth fakes;
- token rotation;
- revoke;
- isolation;
- unavailable platform.


## Criterios de aceptación

- [x] Permisos mínimos: Instagram solo solicita `instagram_business_basic`; no se solicita `instagram_business_content_publish`.
- [x] Tokens server-only: AES-256-GCM con datos asociados a workspace, proveedor y campo; nunca se devuelve el token ni el sobre.
- [x] Revocación: se intenta revocar en el proveedor y siempre se eliminan localmente los tokens; el resultado remoto no se sobredeclara.
- [x] No scraping: no existe lector de timelines ni endpoint de publicación/importación.


## Prohibiciones


- No prometer TikTok trends.
- No X sin billing.
- No guardar token plano.

## Verificación

- Suite OAuth/social: `112 passed`.
- E2E social con PostgreSQL de pruebas: `16 passed`.
- Migración social desde base vacía: `alembic upgrade 023` y `alembic current` → `023`.
- Ruff backend: `All checks passed!`.
- Suite frontend: `165 passed`.
- TypeScript: `tsc --noEmit` sin errores.
- No se ejecutaron proveedores sociales reales ni se almacenaron credenciales reales.

La continuación de WAVE-013 actualizó las aserciones históricas del head de migraciones de `023` a `024`; la migración social propia continúa siendo `023`.


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
