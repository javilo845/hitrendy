# Snippets de integración

Estos snippets son plantillas de configuración. No contienen claves reales y
no deben copiarse al cliente web.

## Dónde poner las APIs

Las claves van únicamente en el entorno del backend:

1. Copia `.env.example` a `.env` en la raíz del repositorio.
2. Completa `AI_API_KEY` con la clave de OpenRouter.
3. No uses `NEXT_PUBLIC_` para ninguna clave de proveedor.
4. No subas `.env` a Git.

El backend lee `AI_PROVIDER`, `AI_BASE_URL`, `AI_MODEL` y `AI_API_KEY`. El
frontend solamente llama a `/api/v1`; nunca recibe la clave.

## Snippets disponibles

- [openrouter.env.example](openrouter.env.example): variables mínimas para
  publicaciones y guiones.
- [openrouter-vision.env.example](openrouter-vision.env.example): configuración
  opcional para análisis visual con un modelo multimodal compatible.
- [run-local.sh](run-local.sh): arranque local del backend.
- [smoke-openrouter.sh](smoke-openrouter.sh): comprobación directa del endpoint
  compatible con OpenAI sin imprimir la clave.

## Orden recomendado

1. Empieza con `VISION_PROVIDER=demo`.
2. Configura primero generación de publicaciones y guiones.
3. Ejecuta el smoke test del proveedor.
4. Levanta la aplicación y prueba Studio.
5. Configura visión solo después de que el flujo de texto funcione.

Los modelos gratuitos de OpenRouter pueden tener límites y disponibilidad
variable. Para la entrega, conserva siempre el proveedor demo como fallback.
