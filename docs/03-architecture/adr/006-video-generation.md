---
id: ADR-006
kind: architecture_decision
status: under_review
related: [ADR-004, ADR-005]
---

# ADR-006: Jobs de video asíncronos con presupuesto y Asset privado

## Contexto

La generación de video puede ser lenta, pagada y no idempotente en el límite
entre la aplicación y el proveedor. El resultado también necesita mantenerse
editable y privado dentro del flujo de assets de HiTrendy.

## Decisión

- La API separa preflight, confirmación y ejecución. La confirmación reserva una
  unidad diaria por workspace y encola un job durable.
- Un worker con `FOR UPDATE SKIP LOCKED` y token de fencing procesa los estados.
  El contador de submits no se consume durante polling: cada poll reserva un
  lease explícito y se registra en `poll_count`; un job pendiente puede seguir
  consultándose hasta `VIDEO_GENERATION_MAX_POLL_SECONDS`.
  Después de cruzar `submitting`, un timeout o la pérdida del worker se cierra
  como `execution_unknown`; no se reenvía automáticamente una solicitud que
  podría haber sido cobrada.
- El proveedor se consume mediante `VideoGenerationProvider`. La interfaz de
  descarga recibe la duración persistida del job, no estado local del proceso.
- Los bytes validados se almacenan en object storage privado y se representan
  mediante un `Asset`; la API entrega únicamente una URL firmada de vida corta.
- El job conserva la referencia lógica de la imagen fuente aprobada y el actor
  que confirmó la reserva. Si la fuente falta antes del submit, se falla y se
  devuelve la reserva al ledger original; después del submit no se vuelve a
  enviar el job remoto.
- El proveedor demo permanece offline y la capacidad queda deshabilitada por
  defecto. Existe un adapter opcional de OpenAI/Sora seleccionado mediante
  variables de entorno y protegido por allowlist, presupuesto y confirmación.
  Otros proveedores comerciales requieren implementar el mismo puerto y su
  contrato de errores.

## Consecuencias

- Un reinicio del worker no altera la duración solicitada ni provoca un segundo
  submit ambiguo.
- El presupuesto puede reservarse y reembolsarse de forma auditable, pero un
  resultado ambiguo no inventa crédito.
- La UI puede consultar un job sin recibir prompts, credenciales, respuestas de
  proveedor, identificadores completos ni rutas internas.
- Añadir un proveedor requiere implementar el puerto, validar sus artefactos y
  definir cómo reporta costo y estados; no requiere cambiar el dominio ni la
  persistencia pública.
