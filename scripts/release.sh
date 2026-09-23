#!/usr/bin/env bash
# Start the application server.
#
# Deployment flow (do NOT run migrations inside this process):
#   1. Build the image.
#   2. Run migration once: bash scripts/migrate.sh
#   3. Start one or more replicas: bash scripts/release.sh
#   4. Check readiness via /health/ready.
#
set -euo pipefail

cd starter/backend

echo "--- Starting application ---"
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
