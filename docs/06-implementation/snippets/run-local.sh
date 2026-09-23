#!/usr/bin/env bash
set -euo pipefail

# Ejecutar desde la raíz del repositorio después de crear .env.
npm install
PYTHONPATH=starter/backend .venv/bin/alembic -c starter/backend/alembic.ini upgrade head

# En otra terminal ejecuta `npm run web:dev`.
PYTHONPATH=starter/backend .venv/bin/uvicorn \
  app.main:app \
  --app-dir starter/backend \
  --reload \
  --port 8000
