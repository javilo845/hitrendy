---
id: IMPL-PROVIDER-KEYS
kind: operational-setup
status: accepted
---

# Claves y activación de proveedores

Este archivo es la lista que debe recibir la persona que despliegue HiTrendy.
Las claves se configuran únicamente en el entorno del backend; nunca se ponen
en `starter/web`, en variables `NEXT_PUBLIC_*`, en el navegador ni en el
repositorio.

## Mínimo para texto, visión, imágenes y video con OpenAI

Se puede reutilizar una sola clave:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

AI_PROVIDER=openai-compatible
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=<modelo-de-texto-habilitado>

VISION_PROVIDER=openai-compatible
VISION_BASE_URL=https://api.openai.com/v1
VISION_MODEL=<modelo-con-vision-habilitado>

IMAGE_GENERATION_ENABLED=1
IMAGE_PROVIDER=openai
IMAGE_GENERATION_MODEL=gpt-image-2
IMAGE_GENERATION_ALLOWED_MODELS=gpt-image-2

VIDEO_GENERATION_ENABLED=1
VIDEO_PROVIDER=openai
VIDEO_GENERATION_MODEL=sora-2
VIDEO_GENERATION_ALLOWED_MODELS=sora-2
VIDEO_GENERATION_ALLOWED_DURATIONS=16,20
```

`AI_API_KEY` y `VISION_API_KEY` pueden quedarse vacías: el backend las
resuelve desde `OPENAI_API_KEY`. La URL también tiene ese fallback. Si el
equipo elige otro modelo de texto o imagen, debe ponerlo tanto en la variable
de modelo como en su `*_ALLOWED_MODELS` correspondiente.

La generación de imágenes y video es de pago y conserva una confirmación,
presupuesto diario, idempotencia y un worker separado. El `docker-compose.yml`
ya incluye `image-worker` y `video-worker`; en otros despliegues deben ejecutar:

```bash
PYTHONPATH=starter/backend python -m app.images.worker --interval 5 --batch 5
PYTHONPATH=starter/backend python -m app.videos.worker --interval 5 --batch 5
```

La API de video Sora 2 figura actualmente como deprecada y con cierre
programado para el 24 de septiembre de 2026. Para una feria dentro de ese
periodo puede activarse si la cuenta tiene acceso, pero no debe venderse como
una integración estable de largo plazo sin sustituir el adapter.

## Tendencias

OpenAI no proporciona aquí la fuente de tendencias. Hay tres rutas disponibles:

- RSS: no requiere clave; activar `TREND_ANALYSIS_ENABLED=1`,
  `RSS_TRENDS_ENABLED=1` y conservar una URL HTTPS en
  `RSS_TRENDS_ALLOWLIST`.
- YouTube: requiere `YOUTUBE_API_KEY`, además de
  `YOUTUBE_TRENDS_ENABLED=1`.
- Google Trends mediante SerpApi: requiere `SERPAPI_API_KEY`, además de
  `SERPAPI_TRENDS_ENABLED=1`.

Las fuentes se consultan como señales acotadas y con caché; no convierten el
MVP en un panel de escucha social.

## Conexiones sociales

La implementación real disponible es la conexión OAuth de Instagram; conectar
una cuenta no publica automáticamente contenido. Para activarla se necesitan:

```dotenv
SOCIAL_CONNECTIONS_ENABLED=1
INSTAGRAM_CONNECTIONS_ENABLED=1
INSTAGRAM_CLIENT_ID=...
INSTAGRAM_CLIENT_SECRET=...
INSTAGRAM_REDIRECT_URI=https://api.example.com/api/v1/social/instagram/callback
SOCIAL_PUBLIC_BACKEND_URL=https://api.example.com
SOCIAL_TOKEN_ENCRYPTION_KEY=<base64-de-32-bytes>
REDIS_PROVIDER=redis
REDIS_URL=rediss://...
```

La URI de redirección debe coincidir exactamente con la registrada en Meta. La
conexión no habilita publicación, scraping ni métricas: esas capacidades no
están implementadas en el MVP. TikTok y X permanecen deshabilitados hasta que
exista un adapter autorizado para cada red.

## Infraestructura y servicios opcionales

Además de las claves de proveedor, staging/producción necesita sus propios
secretos de operación: `DATABASE_URL`, `JWT_SECRET`, almacenamiento privado
(`SUPABASE_SERVICE_ROLE_KEY` o `OBJECT_STORAGE_*`), `REDIS_URL`,
`ALLOWED_ORIGINS`, `ALLOWED_HOSTS` y `FRONTEND_URL`.

Para verificación de correo y recuperación de cuenta, activar `EMAIL_PROVIDER=resend`
y proporcionar `RESEND_API_KEY`. Google Sign-In es opcional y usa
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` y `GOOGLE_REDIRECT_URI`.

No se deben compartir claves en el chat, commits, logs o capturas. El proveedor
debe recibirlas desde el gestor de secretos del entorno.
