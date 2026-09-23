# WAVE-013 — Video asíncrono

## Estado

Completada y aprobada — 2026-08-02. La implementación base conserva el
proveedor demo offline y la capacidad queda deshabilitada por defecto. Después
se añadió un adapter opcional de OpenAI/Sora sin cambiar el contrato durable.
## Objetivo

Generar clips verticales editables con límites estrictos después de cerrar
imagen y costos, dejando el resultado como un `Asset` privado.

## Alcance implementado

- storyboard determinista y editable como fallback, sin llamar a un modelo;
- puerto `VideoGenerationProvider` reemplazable, proveedor demo con fixtures
  MP4 reales de 5 y 10 segundos y adapter OpenAI/Sora para renders 16/20
  segundos;
- preflight firmado, confirmación explícita e idempotencia;
- jobs asíncronos durables con polling acotado, timeout, fencing y
  `execution_unknown` después de cruzar el límite del proveedor;
- `attempt_count` reservado para preparación/submit, `poll_count` separado y
  leases explícitos para `provider_pending`; los polls no consumen el máximo de
  submits y continúan hasta `VIDEO_GENERATION_MAX_POLL_SECONDS`;
- presupuesto diario UTC por workspace, con reserva antes del job y reembolso
  únicamente si el proveedor todavía no fue alcanzado;
- actor confirmador persistido en `requested_by_user_id`, usado por el worker
  ejecutable para registrar uso y costo sin recibir un `user_id` inyectado;
- referencia lógica inmutable de `source_asset_id`: si la fuente desaparece
  antes del submit se falla y se reembolsa el ledger original; después del
  submit no se reenvía el job remoto;
- almacenamiento privado como `Asset`, validación de contenedor, duración,
  formato vertical y tamaño antes de marcar el job como exitoso;
- URL firmada con dominio separado, TTL y autorización por workspace;
- polling desde la interfaz, estados de carga, error, disabled, fallback y
  éxito, sin publicación ni programación en redes sociales.

## Arquitectura y secuencia

1. `POST /videos/storyboard` produce un storyboard editable con contexto del
   negocio y no consume presupuesto.
2. `POST /videos/preflight` valida formato, duración, proyecto, imagen de
   origen, capacidad y saldo; firma exactamente los campos que pueden llegar al
   proveedor.
3. `POST /videos/jobs` exige `confirmed=true`, token vigente y
   `Idempotency-Key`, reserva una unidad y encola el job.
4. El worker reclama con `FOR UPDATE SKIP LOCKED`, guarda la ruta aprobada y
   llama `submit` una sola vez.
5. El siguiente ciclo consulta `check`; si está listo descarga pasando la
   duración persistida, valida el MP4 (ftyp, moov, mdat no vacío, handler video,
   H.264/AVC, dimensiones, duración, ratio y tamaño), lo guarda en object
   storage y crea un `Asset` de tipo `video`.
6. `GET /videos/jobs/{id}` devuelve únicamente campos públicos y una URL
   firmada regenerable. `GET /videos/files/{asset_id}` sirve el objeto completo
   y privado; no se simula soporte `Range`.

Estados durables: `queued`, `preparing`, `submitting`, `provider_pending`,
`downloading`, `succeeded`, `failed`, `cancelled` y `execution_unknown`.
`submitting` no se reintenta automáticamente porque no es posible saber si el
proveedor recibió la solicitud; el barrido lo cierra como ambiguo sin reembolso.

## Contratos y límites

- Formato único: `9:16`.
- Duraciones permitidas por configuración: 5 y 10 segundos en demo; 16 y 20
  segundos con el adapter OpenAI.
- El provider demo solo acepta fixtures exactas de 5 y 10 segundos; no existe
  redondeo a la fixture más cercana. El storyboard y la UI consumen la misma
  allowlist servida por backend.
- Presupuesto inicial: 2 unidades diarias por workspace, limitado también por
  `VIDEO_GENERATION_DAILY_BUDGET`.
- `VIDEO_GENERATION_POLL_INTERVAL_SECONDS`,
  `VIDEO_GENERATION_MAX_POLL_SECONDS`, timeout, intentos y bytes máximos son
  límites configurables y positivos.
- El demo es válido únicamente en desarrollo/pruebas; producción no puede
  activar video con `VIDEO_PROVIDER=demo`.
- Los contratos públicos no exponen prompts, respuestas del proveedor,
  `provider_job_id` completo, secretos ni rutas de storage.

## Migración y datos

La migración `024_video_generation` añade `assets.duration_seconds` y crea
`video_generation_jobs` y `video_generation_budgets`, con constraints para
estado, formato, duración, presupuesto y unicidad de
`(provider, provider_job_id)`. También persiste el actor, los contadores
separados de submit/poll/download y un índice de polling. `source_asset_id` es
una referencia lógica sin `ON DELETE SET NULL`, para no cambiar la aprobación
silenciosamente. El job guarda solo referencias y metadatos necesarios; los
bytes permanecen fuera de PostgreSQL.

## Seguridad

- Todos los jobs, proyectos, imágenes de origen y assets se filtran por
  workspace.
- El approval token tiene expiración y fingerprint de todos los campos
  editables; la firma de preflight está separada de la firma de URL.
- Los bytes del proveedor se validan antes de persistir el asset.
- La clave de object storage la genera el servidor y el endpoint de archivo
  verifica la firma antes de consultar existencia o storage.
- No se publican clips automáticamente. Los proveedores reales solo se
  contactan cuando el operador habilita explícitamente la ruta y el usuario
  confirma un job.

## Operación local/beta

El servidor HTTP no procesa esta cola. Con PostgreSQL de prueba o una
configuración beta autorizada, el proceso operativo es:

```bash
cd starter/backend
source ../../.venv/bin/activate
PYTHONPATH=. python -m app.videos.worker --once --batch 5
PYTHONPATH=. python -m app.videos.worker --interval 5 --batch 5
```

`--once` ejecuta un ciclo reproducible; el segundo comando mantiene el worker
activo hasta `SIGINT`/`SIGTERM`. Debe ejecutarse con la misma `DATABASE_URL`,
storage y ruta de provider que la API. La demo usa el provider offline. Para
OpenAI, la misma orden de worker usa la clave del entorno del backend y
conserva el estado ambiguo si un submit expira.

## Pruebas y aprobación

La suite de video ahora cubre polling múltiple, lease activo/vencido,
idempotencia, presupuesto concurrente y refund histórico, actor del worker,
reinicio, source asset, flag, ruta, errores de descarga/storage, rechazo del
provider después de `submitting`, compensación post-storage, MP4 inválido,
URLs, aislamiento, purge y ausencia de publicación. La migración cubre el
roundtrip `023 → 024 → 023 → 024`, constraints PostgreSQL y paridad ORM.

La validación técnica registrada en esta revisión es: migraciones PostgreSQL
`27 passed`, video unitario `20 passed`, video E2E `28 passed`, E2E completa
`77 passed`, backend sin E2E ni proveedores reales `729 passed`, backend
completo sin proveedores reales `806 passed, 3 deselected`, y frontend
completo `167 passed` con typecheck, lint y build exitosos. La wave fue revisada y aprobada después de verificar el diff real y las salidas completas.
- `tests/test_capability_registry.py`: fallback `storyboard` y capacidad
  disabled por defecto cubiertos.
- Migraciones PostgreSQL: 27 passed; head 024, tablas de video y columna de
  duración comprobadas.
- Frontend existente de la wave: tests, typecheck y lint conservados en la
  verificación de entrega.

## Criterios de aceptación

- [x] No hay gasto ilimitado: capacidad apagada por defecto, preflight, límites
  de duración, presupuesto diario, timeout y máximo de intentos.
- [x] El estado asíncrono es durable y el worker no reenvía un submit ambiguo.
- [x] El fallback de storyboard es editable y no requiere proveedor.
- [x] El uso se registra sin convertir un costo desconocido en cero.
- [x] El resultado validado queda como `Asset` privado con URL firmada.
- [x] No hay publicación automática, scheduling de publicaciones ni scraping;
  el proveedor OpenAI es opcional y no se activa por defecto.

## Limitaciones explícitas

Esta wave no incorpora webhooks externos, cancelación desde la UI, edición/render
posterior del MP4, soporte HTTP `Range`, publicación ni métricas de redes. Esas
capacidades requieren contratos y autorización propios; no forman parte de
WAVE-013. Sora 2 aparece deprecado en la documentación actual de OpenAI y tiene
cierre programado para el 24 de septiembre de 2026; el adapter debe sustituirse
antes de depender de video a largo plazo.

No hacer commit ni push automáticamente. Dejar el working tree revisable.
