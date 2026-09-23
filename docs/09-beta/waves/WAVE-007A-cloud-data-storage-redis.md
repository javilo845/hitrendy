# WAVE-007A — PostgreSQL, Storage y Redis administrados

## Objetivo

Preparar el código y documentación para Supabase PostgreSQL/Storage y Upstash Redis sin romper local ni E2E.

## Contexto del repositorio


El backend ya usa PostgreSQL, S3-compatible storage y exige Redis en producción.


## Alcance


- Config remota.
- SSL/connection pooling.
- Storage S3.
- Buckets/prefixes privados.
- Redis TLS.
- scripts de migración y smoke.
- backup básico.


## Inspección obligatoria

Antes de editar:


- config;
- database engine;
- storage adapter;
- uploads;
- rate limit/Redis;
- `.env.example`;
- deploy docs;
- E2E.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Verificar URLs de Supabase y pooler.
2. Configurar SQLAlchemy para SSL y pool.
3. Reutilizar adapter S3 con endpoint Supabase.
4. Prefijos `workspace_id/...`.
5. URLs firmadas, no públicas por defecto.
6. Conectar Upstash Redis mediante URL soportada por cliente actual o adapter.
7. Separar local/staging/beta.
8. Crear scripts no destructivos de migrate/verify.
9. Documentar export/restore.


## Contratos


No guardar service role/S3 secret en frontend. El backend entrega URLs firmadas cortas.


## Pruebas obligatorias


- DB remota de staging;
- migrations hasta head;
- upload/download;
- aislamiento por workspace;
- Redis health/rate limit;
- local tests;
- E2E;
- no secretos en git.


## Criterios de aceptación


- [ ] Base remota funciona.
- [ ] Storage persiste.
- [ ] Redis funciona.
- [ ] Local sigue funcionando.
- [ ] E2E siguen aislados.
- [ ] No hay secretos.


## Prohibiciones


- No cambiar a Supabase Auth.
- No usar filesystem de Render.
- No usar DB de producción en tests.


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
