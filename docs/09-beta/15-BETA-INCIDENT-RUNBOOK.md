---
id: BETA-INCIDENT-RUNBOOK
kind: operations
status: accepted
---

# Runbook de incidentes de la beta cerrada

Este documento sirve para staging y para las sesiones de beta con una persona
operadora identificada. La beta usa servicios gratuitos o compartidos; por eso
estos son objetivos internos de operación y no un SLA público.

## Señales y objetivos internos

- `GET /health/live`: el proceso responde.
- `GET /health/ready`: la aplicación puede usar la base de datos y sus
  dependencias configuradas.
- `GET /health/metrics`: solicitudes, respuestas 5xx, duración acumulada y
  códigos de error del proceso actual.
- Cada respuesta lleva `X-Request-Id`; usarlo para unir reporte, logs y
  despliegue.

Durante una sesión atendida, el objetivo es detectar un 5xx sostenido en cinco
minutos, responder al usuario afectado en quince minutos y registrar la causa
antes de cerrar el incidente. Un reinicio puede perder las métricas del proceso;
el ledger de uso y las auditorías administrativas son persistentes.

## Clasificación y primera respuesta

1. Confirmar hora, entorno, URL, usuario afectado y `X-Request-Id`.
2. Ejecutar `python scripts/beta_readiness_check.py --base-url ...`.
3. Revisar `/health/ready`, tasa de 5xx, logs de error y el último release.
4. No copiar tokens, contraseñas, cookies, prompts privados ni claves en el
   ticket.
5. Si existe riesgo de costo o abuso, pausar la capacidad afectada con su
   flag de entorno y conservar la evidencia mínima necesaria.

Severidad interna:

- **S1:** acceso de terceros, pérdida de datos o gasto no autorizado. Pausar
  tráfico, preservar logs y escalar inmediatamente.
- **S2:** beta completa bloqueada o recuperación de contraseña inutilizable.
  Pausar el release y comunicar el estado a los testers.
- **S3:** fallo aislado con alternativa manual. Registrar y corregir en el
  siguiente ciclo.

## Alertas

El proceso marca `error_rate_high` cuando el porcentaje de respuestas 5xx
alcanza `ALERT_ERROR_RATE_PERCENT` y marca el límite de costos desde la vista
de uso cuando el gasto llega a `COST_ALERT_THRESHOLD_PERCENT` del presupuesto.
En despliegues sin un proveedor de alertas externo, una persona debe consultar
`/health/metrics` y los logs durante cada sesión. `ERROR_TRACKING_PROVIDER=logging`
no envía datos a terceros; Sentry sólo se puede habilitar con un DSN
explícito y una revisión de privacidad.

## Release, migraciones y rollback

Antes del release:

```bash
python scripts/backup.py --database-url "$DATABASE_URL" --output-dir ./backups
PYTHONPATH=starter/backend python -m alembic upgrade head
python scripts/beta_readiness_check.py --base-url https://staging.example
python scripts/load_smoke.py --base-url https://staging.example --requests 20 --concurrency 4
```

Ejecutar la migración una sola vez como release command, nunca desde cada
réplica. Si readiness falla, mantener la aplicación anterior o hacer rollback
de la imagen; no borrar migraciones aplicadas. Si hay cambio de datos, detener
la escritura y usar el drill de restauración:

```bash
python scripts/restore_drill.py \
  ./backups/backup.dump \
  --target-database-url "$DATABASE_URL" \
  --dry-run
```

El comando restaura a un destino con sufijo `_restore` cuando no se proporciona
confirmación explícita. La restauración productiva requiere una aprobación
separada y `--confirm RESTORE`; hacerla sólo después de verificar el manifiesto
SHA-256 y el destino exacto.

## Acceso, uso y soporte

Crear o revocar invitaciones únicamente con la CLI auditada:

```bash
PYTHONPATH=starter/backend python -m app.operations.invite_cli create \
  --actor ops@example.com --reason "sesión de beta" --email tester@example.com
```

Resetear uso sin editar eventos históricos:

```bash
PYTHONPATH=starter/backend python -m app.admin.usage reset \
  --email tester@example.com --actor ops@example.com \
  --reason "reintento de sesión" --confirm RESET_USAGE
```

Los comandos requieren que el actor esté en `HITRENDY_ADMIN_IDENTITIES`,
registran actor, motivo, resultado y fecha en `admin_audit_events`, y nunca
imprimen claves de proveedor. Los reportes de abuso y el formulario de feedback
entran por `/api/v1/abuse/reports` y `/api/v1/feedback`; soporte responde desde
el correo configurado en `SUPPORT_EMAIL`.

## Comunicación y cierre

Comunicar a los testers sólo: impacto, capacidades afectadas, alternativa,
próxima actualización y si deben repetir una acción. No afirmar disponibilidad
garantizada ni publicar detalles privados. Al cerrar, registrar causa raíz,
ventana, request IDs, cambios realizados, datos afectados, seguimiento y
resultado del smoke posterior.
