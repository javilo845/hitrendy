#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000/api/v1}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  printf 'No se encontró Python (%s). Instala Python 3.12 o define PYTHON_BIN.\n' "$PYTHON_BIN" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  printf 'No se encontró npm. Instala Node.js 20 y npm antes de validar.\n' >&2
  exit 1
fi

printf '%s\n' '== Backend: Ruff =='
(
  cd "$ROOT_DIR/starter/backend"
  "$PYTHON_BIN" -m ruff check .
)

printf '%s\n' '== Backend: suite rápida =='
(
  cd "$ROOT_DIR/starter/backend"
  PYTHONPATH=. "$PYTHON_BIN" -m pytest -m "not e2e"
)

printf '%s\n' '== Frontend: tests =='
npm --prefix "$ROOT_DIR" run web:test

printf '%s\n' '== Frontend: typecheck =='
npm --prefix "$ROOT_DIR" run web:typecheck

printf '%s\n' '== Frontend: lint =='
npm --prefix "$ROOT_DIR" run web:lint

printf '%s\n' '== Frontend: build =='
npm --prefix "$ROOT_DIR" run web:build

printf '%s\n' 'Validación rápida completada.'
