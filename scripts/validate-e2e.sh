#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
TEST_DATABASE_URL="${TEST_DATABASE_URL:-postgresql+psycopg://hitrendy:hitrendy@localhost:5433/hitrendy_test}"
export TEST_DATABASE_URL

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  printf 'No se encontró Python (%s). Instala Python 3.12 o define PYTHON_BIN.\n' "$PYTHON_BIN" >&2
  exit 1
fi

database_name="${TEST_DATABASE_URL##*/}"
database_name="${database_name%%\?*}"
if [[ "$database_name" != *_test && "$database_name" != *_e2e ]]; then
  printf 'TEST_DATABASE_URL debe apuntar a una base cuyo nombre termine en _test o _e2e.\n' >&2
  exit 1
fi

if [[ "$TEST_DATABASE_URL" == "postgresql+psycopg://hitrendy:hitrendy@localhost:5433/hitrendy_test" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    printf 'No se encontró Docker para iniciar postgres-test. Define TEST_DATABASE_URL con un PostgreSQL ya levantado.\n' >&2
    exit 1
  fi
  printf '%s\n' '== PostgreSQL E2E: iniciar servicio aislado =='
  docker compose -f "$ROOT_DIR/docker-compose.yml" up -d postgres-test
  for attempt in $(seq 1 30); do
    if docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres-test \
      pg_isready -U hitrendy -d hitrendy_test >/dev/null 2>&1; then
      break
    fi
    if [[ "$attempt" == 30 ]]; then
      printf '%s\n' 'PostgreSQL de pruebas no alcanzó readiness.' >&2
      exit 1
    fi
    sleep 1
  done
fi

printf '%s\n' '== Alembic: upgrade head =='
(
  cd "$ROOT_DIR/starter/backend"
  PYTHONPATH=. "$PYTHON_BIN" -m alembic upgrade head
  PYTHONPATH=. "$PYTHON_BIN" -m alembic upgrade head
  PYTHONPATH=. "$PYTHON_BIN" -m alembic current
)

printf '%s\n' '== Backend: pruebas PostgreSQL de migraciones =='
(
  cd "$ROOT_DIR/starter/backend"
  POSTGRES_MIGRATION_DATABASE_URL="$TEST_DATABASE_URL" \
    RUN_POSTGRES_MIGRATION_TESTS=1 \
    PYTHONPATH=. "$PYTHON_BIN" -m pytest tests/test_migrations_postgres.py -v
)

printf '%s\n' '== Alembic: restaurar head después de las pruebas de migración =='
(
  cd "$ROOT_DIR/starter/backend"
  PYTHONPATH=. "$PYTHON_BIN" -m alembic upgrade head
)

printf '%s\n' '== Backend: E2E =='
(
  cd "$ROOT_DIR/starter/backend"
  PYTHONPATH=. "$PYTHON_BIN" -m pytest -m e2e -v
)

printf '%s\n' 'Pruebas E2E y migraciones completadas.'
