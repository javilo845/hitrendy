# Modelo de datos y migraciones propuestas

## 1. Principios

- Mantener UUID/IDs y convenciones actuales.
- Una migración por cambio coherente.
- PostgreSQL es la referencia.
- Conservar compatibilidad con SQLite solo donde la suite rápida la requiera.
- No modificar migraciones históricas salvo incompatibilidad comprobada.
- La siguiente revisión debe partir del head real en el momento de implementación.

## 2. Registro temporal

### `pending_signups`

Campos mínimos:

```text
id
email_normalized
name
password_hash nullable
oauth_provider nullable
oauth_subject nullable
interface_locale
draft_json
current_step
token_hash
expires_at
created_at
updated_at
```

Reglas:

- Nunca guardar contraseña en texto.
- Token aleatorio solo en cookie; DB guarda hash.
- Email reservado mientras el draft esté vigente.
- Expiración, por ejemplo, 24 horas.
- Índices por email y token hash.
- Google y contraseña no requieren exactamente los mismos campos.

## 3. Usuarios e identidad

Cambios propuestos:

### `users`

```text
interface_locale
status
deleted_at nullable
```

Estados:

```text
active
deleting
disabled
```

### `oauth_accounts`

```text
id
user_id
provider
provider_subject
email_at_link_time
created_at
last_login_at
```

Restricción única:

```text
(provider, provider_subject)
```

## 4. Un negocio por cuenta beta

Conservar `Workspace` internamente.

Aplicar:

```text
un usuario owner
→ un workspace primario
→ un business activo
```

Opciones:

- restricción única `businesses.workspace_id`;
- o campo `is_primary` con índice parcial único.

Preferencia beta: una restricción simple por workspace, siempre que los tests actuales no dependan de múltiples negocios.

## 5. Preferencias

### `user_preferences`

```text
user_id
interface_locale
timezone
created_at
updated_at
```

### Negocio

Agregar o normalizar:

```text
content_locale
website_url
onboarding_completed_at
```

Usar códigos BCP 47:

```text
es
en
pt-BR
es-HN
```

La interfaz inicial solo expone `es`, `en`, `pt`.

## 6. Registro de capacidades

### `integration_configs`

No almacenar la clave directamente si el secreto vive en el proveedor de hosting.

```text
key
enabled
tier
environment
configuration_metadata_json
updated_at
```

### `integration_health`

```text
integration_key
status
last_checked_at
last_success_at
last_error_code
quota_limit nullable
quota_used nullable
quota_reset_at nullable
```

## 7. Model routing

### `model_routes`

```text
capability
quality_tier
provider
model_id
enabled
requires_paid
fallback_priority
input_modalities
output_modalities
max_cost_per_operation nullable
updated_at
```

Restricción única:

```text
(capability, quality_tier, provider, model_id)
```

No guardar el catálogo completo de OpenRouter como fuente de verdad permanente. Cachearlo y fijar rutas aprobadas.

## 8. Uso

### `usage_events`

Ledger inmutable:

```text
id
user_id
workspace_id
capability
provider
model_id
units
prompt_tokens nullable
completion_tokens nullable
provider_cost_usd nullable
request_id
generation_job_id nullable
created_at
```

### `usage_allowances`

```text
workspace_id
period_type
period_start
period_end
recommendation_limit nullable
text_limit nullable
image_limit nullable
video_limit nullable
enforcement_mode
```

### `usage_adjustments`

```text
id
workspace_id
actor_user_id
capability nullable
delta
reason
created_at
```

No editar directamente el ledger.

## 9. Tendencias

### `trend_runs`

```text
id
region
started_at
completed_at
status
trigger
source_set_hash
```

### `trend_items`

```text
id
canonical_topic
region
language
first_seen_at
last_seen_at
freshness_score
growth_score
cross_source_score
confidence
```

### `trend_evidence`

```text
id
trend_item_id
source
source_url
external_id nullable
published_at nullable
observed_at
metrics_json
title
snippet
```

### `business_trend_scores`

```text
business_id
trend_item_id
relevance_score
platform_fit_score
final_score
explanation_json
computed_at
```

## 10. Generación multimedia

### `generation_jobs`

```text
id
workspace_id
user_id
capability
status
provider
model_id
quality_tier
request_hash
idempotency_key
provider_job_id nullable
result_asset_id nullable
cost_usd nullable
error_code nullable
created_at
updated_at
completed_at nullable
```

### `generated_assets`

Reutilizar el modelo de archivos/artefactos existente cuando sea posible. Evitar dos sistemas paralelos.

## 11. Eliminación de cuenta

### `account_deletion_jobs`

```text
id
user_id
requested_at
status
last_step
completed_at nullable
error_code nullable
```

Flujo:

1. Marcar cuenta `deleting`.
2. Revocar sesiones.
3. Bloquear login.
4. Borrar/anonimizar filas.
5. Borrar objetos Storage.
6. Conservar solo auditoría mínima sin PII, si la política lo permite.

## 12. Estrategia de migración

Cada subwave debe:

1. Crear migración.
2. Aplicar desde DB vacía.
3. Aplicar sobre DB en head anterior.
4. Repetir `upgrade head`.
5. Ejecutar pruebas PostgreSQL.
6. Probar constraints.
7. Documentar downgrade si es seguro.
8. No borrar datos reales silenciosamente.
