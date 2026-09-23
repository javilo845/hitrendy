---
id: BETA-THREAT-REVIEW
kind: security-review
status: accepted
date: 2026-08-02
---

# Threat review de la beta cerrada

Esta revisión cubre los límites que cambian al pasar de staging atendido a una
beta por invitación. No sustituye una auditoría externa ni un pentest.

## Hallazgos y controles

| Riesgo | Control implementado | Verificación |
| --- | --- | --- |
| Enumeración de cuentas por recuperación | Respuesta genérica y mismo estado `202` para correos conocidos/desconocidos | `test_password_reset_is_generic_and_single_use` |
| Robo o repetición de enlace | Token aleatorio, hash en base, expiración, uso único y revocación de sesiones | tests de reset |
| Compartir invitaciones | Código hash en reposo, expiración, asociación opcional a correo, bloqueo al redimir y revocación CLI | test de beta cerrada |
| Acceso entre workspaces | Dependencias de sesión y membresía existentes; feedback/abuso usan el workspace autorizado | suite de aislamiento existente |
| CSRF y abuso de endpoints | CSRF, cookies HttpOnly, rate limit para auth, reset, feedback y abuso | suite de seguridad existente |
| Fuga de secretos en métricas/logs/backups | Métricas de baja cardinalidad, tracker de logging sin payload, URLs PostgreSQL sin password en argv y `PGPASSWORD` sólo en entorno | tests de backup y revisión de logs |
| Costo inesperado de IA | Presupuesto mensual, modos `off`/`soft`/`hard`, alerta de porcentaje y bloqueo previo en `hard` | test de cost cap |
| Restaurar sobre producción por accidente | Restore exige destino `_restore` o confirmación explícita; se verifica manifiesto SHA-256 | tests de backup/restore |
| Política o soporte ausentes | Páginas versionadas, endpoint público de políticas, feedback y reportes de abuso | smoke browser desktop/móvil |

## Riesgos aceptados para esta beta

- El contador de métricas es por proceso; un reinicio lo reinicia y una
  instalación con varias réplicas necesita un agregador externo.
- El tracker incluido registra eventos de error de forma segura, pero no envía
  alertas a un tercero hasta configurar y revisar un DSN.
- La verificación de correo permanece desactivada mientras la beta usa el
  proveedor `demo` o no tiene un dominio transaccional aprobado.
- El almacenamiento local y los proveedores demo sólo son válidos en desarrollo
  y pruebas; staging/producción deben usar sus adaptadores configurados.
- La restauración real de PostgreSQL de staging sigue siendo un gate del
  operador, porque requiere acceso a la base y un destino aislado.

## Decisión de lanzamiento

La beta puede abrirse únicamente con invitaciones individuales, un operador
presente, `BETA_INVITES_ENABLED=1`, `METRICS_ENABLED=1`, presupuesto explícito,
políticas publicadas y el checklist de aceptación marcado. No se autoriza un
lanzamiento público ni se promete SLA con estos controles.
