# HiTrendy backend

FastAPI backend for the authenticated MVP: business context, conversations,
validated content generation, projects, templates, assets, visual review and
workspace authorization. Demo mode uses deterministic providers and requires no
external AI credentials.

```bash
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Run the backend suite from the repository root:

```bash
PYTHONPATH=starter/backend python -m pytest starter/backend/tests
```

Install backend dependencies for development with:

```bash
python -m pip install -r requirements-dev.txt
```

Generation requests accept an optional `Idempotency-Key` header. Reusing the
same key for the same workspace, conversation, and payload returns the already
persisted result instead of creating another artifact. Reusing it with a
different payload returns a conflict, and concurrent requests reserve the key
before invoking the provider.

## Backend E2E Tests

The E2E suite uses the real FastAPI application over HTTP and an isolated
PostgreSQL database. It never uses the development database named `hitrendy`.

### Requisitos

- Docker Compose.
- Python environment with `starter/backend/requirements.txt` installed.
- PostgreSQL de pruebas accesible mediante `TEST_DATABASE_URL`.

The repository includes a separate `postgres-test` service on port `5433`:

```bash
docker compose up -d postgres-test
export TEST_DATABASE_URL='postgresql+psycopg://hitrendy:hitrendy@localhost:5433/hitrendy_test'
```

The E2E fixtures reject URLs that are not PostgreSQL or whose database name
does not end in `_test` or `_e2e`. They reset only that explicitly named test
database, apply all Alembic migrations from an empty schema through `015`,
and run the migration command twice to verify repeatability. The schema is
cleaned again after the E2E session.

### Ejecución

From `starter/backend`:

```bash
source ../../.venv/bin/activate

# Suite rápida, sin PostgreSQL E2E
python -m pytest -m "not e2e"
python -m ruff check .

# Sólo E2E
TEST_DATABASE_URL='postgresql+psycopg://hitrendy:hitrendy@localhost:5433/hitrendy_test' \
  python -m pytest -m e2e -v

# Suite completa
TEST_DATABASE_URL='postgresql+psycopg://hitrendy:hitrendy@localhost:5433/hitrendy_test' \
  python -m pytest
```

Without `TEST_DATABASE_URL`, E2E tests are skipped with an explicit reason;
they are not silently considered passed. If the variable is set but unsafe,
pytest aborts before changing any database.

### Provider de pruebas y cobertura

`tests/e2e/fake_provider.py` injects a deterministic provider into the real
conversation route. It performs no network calls, returns schema-valid social
posts and video scripts, counts invocations, and can simulate temporary,
permanent, and delayed failures. The suite covers health/readiness, migrated
templates, identity and workspace authorization, complete generation and
persistence, idempotency, concurrent requests, variations, normalized errors,
cross-workspace isolation, and replay from a new HTTP session.

## Google Sign-In

Google Sign-In is disabled by default. To enable the backend-controlled OIDC
Authorization Code Flow, configure these server-side variables:

```bash
GOOGLE_SIGN_IN_ENABLED=1
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://api.example.com/api/v1/auth/google/callback
FRONTEND_URL=https://app.example.com
```

The redirect URI must match Google Console exactly. The API uses PKCE, an
HttpOnly temporary OAuth cookie with `SameSite=Lax`, and a database-backed
one-time state. Session and pending-signup cookies stay `SameSite=Strict`; no
Google token or client secret is returned to the browser.

## PostgreSQL, Storage y Redis remotos

HiTrendy conserva SQLAlchemy y Alembic como la única capa de persistencia. Una
URL directa de Supabase o una URL del pooler debe usar el dialecto SQLAlchemy
`postgresql+psycopg://`. Para una base remota, configura SSL explícitamente y
limita el pool por proceso:

```bash
DATABASE_URL='postgresql+psycopg://usuario:contraseña@host:5432/postgres'
DATABASE_SSL_MODE=require
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
DATABASE_POOL_RECYCLE=1800
```

Las URLs `postgres://` y `postgresql://` se normalizan a `psycopg`. Para el
pooler de Supabase usa la URL y puerto publicados por el proyecto, conserva
`DATABASE_SSL_MODE=require` y reduce el pool según los límites de conexión del
plan. Alembic usa la misma URL; ejecuta una sola réplica de migración por
release. Las bases de CI/E2E siguen siendo locales y aisladas.

El almacenamiento se selecciona con `STORAGE_PROVIDER`:

- `local`: desarrollo y pruebas; `OBJECT_STORAGE_LOCAL_DIR` no se expone por API.
- `s3`: compatibilidad existente con MinIO/S3 mediante `OBJECT_STORAGE_*`.
- `supabase`: bucket privado mediante REST con `SUPABASE_URL`,
  `SUPABASE_SERVICE_ROLE_KEY` y `SUPABASE_STORAGE_BUCKET`.
- `disabled`: las cargas devuelven un error normalizado sin escribir archivos.

El service-role key solo se lee en FastAPI. Nunca uses un prefijo
`NEXT_PUBLIC_`, ni hagas público el bucket. Los objetos se guardan bajo
`workspaces/<workspace_id>/assets/...`; el backend autoriza cada lectura y
proxy el contenido, por lo que aún no emite URLs firmadas. Si se añaden en una
wave posterior, deben tener TTL corto y seguir validando workspace en backend.
Crear el bucket privado es una operación administrativa previa al despliegue;
esta aplicación no lo crea automáticamente.

Redis se selecciona con `REDIS_PROVIDER=disabled|memory|redis`:

- `disabled`: no hay caché/estado efímero remoto.
- `memory`: TTL local para desarrollo y tests; no es distribuido.
- `redis`: `REDIS_URL` (`redis://` o `rediss://`, incluido Upstash TCP) o
  `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`.

`REDIS_PREFIX` evita colisiones entre entornos y todas las entradas efímeras
tienen TTL. Define `REDIS_REQUIRED=1` solo cuando una indisponibilidad de Redis
deba bloquear el arranque/readiness; en caso contrario readiness informa
`degraded` sin declarar caída la API. Los estados de health nunca incluyen URLs,
tokens, buckets ni claves.
