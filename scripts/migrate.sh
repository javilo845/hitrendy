#!/usr/bin/env bash
# Run database migrations (one-shot, not inside the web process).
# Usage: bash scripts/migrate.sh
set -euo pipefail

echo "=== Running Alembic migration ==="
cd starter/backend
PYTHONPATH=. python -m alembic upgrade head
echo "Migration complete."
