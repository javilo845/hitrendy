# WAVE-009 — Configuración, idiomas, uso y eliminación

## Objetivo

Completar Configuración con cuenta, negocio, marca, idiomas, uso, privacidad y eliminación.

## Contexto del repositorio


Settings actual edita solo negocio y marca parcial.


## Alcance


- tabs/subroutes;
- es/en/pt;
- content locale;
- account;
- usage;
- privacy;
- delete;
- admin reset CLI.


## Inspección obligatoria

Antes de editar:


- settings page/components;
- i18n setup;
- identity/business;
- usage;
- storage deletion;
- tests.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Elegir librería i18n coherente.
2. Extraer strings principales.
3. Persistir locale.
4. Completar negocio/marca.
5. Uso soft.
6. CLI admin auditada.
7. Delete 202 + purge.
8. Revocar sessions.


## Contratos


La eliminación es inmediata para acceso, asíncrona para purga.


## Pruebas obligatorias


- 3 idiomas;
- content locale;
- usage;
- reset admin;
- non-admin;
- deletion;
- storage purge fake;
- E2E.


## Criterios de aceptación


- [ ] Settings completas.
- [ ] 3 idiomas.
- [ ] Uso visible.
- [ ] Reset auditado.
- [ ] Cuenta eliminada no entra.
- [ ] CI.


## Prohibiciones


- No comando secreto.
- No traducción automática en runtime.
- No ocultar fallos de purga.


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

## Operación

La interfaz distingue el locale de interfaz, persistido en `user_preferences`,
del locale de contenido del negocio. El uso mostrado agrega únicamente eventos
del workspace durante los últimos 30 días y trata costo `null` como desconocido.

La eliminación responde `202`, bloquea el usuario, revoca todas las sesiones y
crea un único `account_purge_job`. La ejecución durable se realiza con
`python -m app.identity.admin_cli status|retry --user-id ... --actor ...
--reason ...`; el actor debe pertenecer a `HITRENDY_ADMIN_IDENTITIES`, cada
acción queda auditada y `retry` requiere `--confirm RETRY`.

La interfaz usa un catálogo estático común (`es`, `en`, `pt`) con fallback a
español. El locale de interfaz se guarda en `user_preferences` y el locale de
contenido permanece en el negocio para las siguientes generaciones. La vista
de uso cubre los últimos 30 días y diferencia costos desconocidos (`null`) de
cero.

El endpoint de eliminación entrega un token opaco de estado únicamente en la
respuesta `202`. Se consulta mediante `X-Deletion-Status-Token`, nunca como
sesión ni como parámetro URL, con expiración y rate limit. Solo devuelve
`pending`, `processing`, `completed` o `failed`; no expone errores internos.
La purga marca una ejecución atascada como reintentable, conserva la cuenta
bloqueada si falla storage y registra el fallo de forma segura para el retry
administrativo.

## Operación de purgas

El servidor web **no ejecuta el worker automáticamente**. Programe un proceso
separado en cada entorno que tenga acceso a la misma base de datos. La opción
recomendada es un servicio supervisado de larga duración:

```bash
python -m app.identity.purge_worker --interval 30 --batch 25
```

Para cron o un job programado, ejecute un ciclo por invocación:

```bash
python -m app.identity.purge_worker --once --batch 25
```

`--interval` (segundos) y `--batch` son opcionales; `--once` procesa un ciclo y
termina. Cada ciclo recupera primero los jobs atascados y después procesa los
jobs `pending` que sean reclamables. Varios workers son seguros: el reclamo usa
locking de base de datos con `SELECT … FOR UPDATE SKIP LOCKED`, de modo que un
job no se procesa dos veces. Los fallos de storage conservan la cuenta
bloqueada y dejan el job disponible para recuperación administrativa.

## Administración auditada

Los comandos se ejecutan desde `starter/backend` y requieren que
`HITRENDY_ADMIN_IDENTITIES` contenga una lista separada por comas de identidades
de operadores autorizados. `--user-id`, `--actor` y `--reason` son obligatorios
en los tres comandos; el motivo se conserva para auditoría.

```bash
python -m app.identity.admin_cli status --user-id USER_ID --actor OPERADOR --reason "motivo"
python -m app.identity.admin_cli retry --user-id USER_ID --actor OPERADOR --reason "motivo" --confirm RETRY
python -m app.identity.admin_cli reset --user-id USER_ID --actor OPERADOR --reason "motivo" --confirm RESET
```

`status` es solo lectura. `retry` procesa inmediatamente la purga pendiente y
exige la confirmación literal `RETRY`. `reset` devuelve a `pending` un job
abandonado, fallido o en proceso para que el worker lo vuelva a reclamar; exige
la confirmación literal `RESET`, no reactiva la cuenta y no ejecuta el worker
por sí mismo. Todas las acciones —incluidos rechazos por identidad o
confirmación— quedan auditadas.
