#!/usr/bin/env bash
set -euo pipefail

: "${AI_API_KEY:?Define AI_API_KEY en tu entorno; no la escribas en este archivo}"
OPENROUTER_BASE_URL="${AI_BASE_URL:-https://openrouter.ai/api/v1}"
OPENROUTER_MODEL="${AI_MODEL:-openrouter/free}"

curl --fail-with-body --silent --show-error \
  "${OPENROUTER_BASE_URL}/chat/completions" \
  -H "Authorization: Bearer ${AI_API_KEY}" \
  -H "Content-Type: application/json" \
  -H "HTTP-Referer: http://localhost:3000" \
  -H "X-Title: HiTrendy local smoke test" \
  -d "$(cat <<JSON
{
  "model": "${OPENROUTER_MODEL}",
  "messages": [
    {"role": "system", "content": "Devuelve únicamente JSON válido con una clave answer."},
    {"role": "user", "content": "Responde con una frase corta confirmando que estás disponible."}
  ],
  "response_format": {"type": "json_object"},
  "temperature": 0.2
}
JSON
)"

printf '\nOpenRouter respondió correctamente.\n'
