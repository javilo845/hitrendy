# Despliegue y entornos

## 1. Propuesta zero-cost

### Datos

- Supabase Free:
  - PostgreSQL;
  - Storage S3 compatible.

### Redis

- Upstash Free.

### Backend

- Render Free para beta cerrada.
- Aceptar:
  - cold start;
  - filesystem efímero;
  - riesgo por tráfico saliente alto.
- No guardar uploads localmente.

### Frontend

No usar Vercel Hobby para una beta comercial.

Opciones:

1. Render Static si la app puede exportarse estáticamente.
2. Render Web Service si requiere SSR.
3. Plan comercial de Vercel cuando exista presupuesto.

La decisión debe salir de una prueba del build actual, no de una suposición.

### Email

- Resend Free.

### IA

- OpenRouter free router para demo/bajo volumen.
- Imágenes y video deshabilitados.

## 2. Servicios necesarios

Variables generales:

```text
DATABASE_URL
REDIS_URL
OBJECT_STORAGE_PROVIDER=s3
OBJECT_STORAGE_ENDPOINT
OBJECT_STORAGE_ACCESS_KEY
OBJECT_STORAGE_SECRET_KEY
OBJECT_STORAGE_BUCKET
AI_PROVIDER=openrouter
OPENROUTER_API_KEY
ALLOWED_ORIGINS
JWT_SECRET
SESSION_COOKIE_NAME
```

Añadir variables por capability, no un solo modelo global.

## 3. Staging antes de beta

- Proyecto Supabase separado o esquema/base separada.
- Buckets separados.
- API key separada.
- datos ficticios;
- correos a dominio controlado;
- Google OAuth en modo test;
- CI deploy opcional después de validación.

## 4. Migraciones

Patrón de release:

1. Backup o snapshot disponible.
2. Ejecutar `alembic upgrade head` como release command.
3. Verificar revisión.
4. Arrancar nueva versión.
5. Health/readiness.
6. Smoke test.
7. Rollback de aplicación si falla.

No ejecutar migraciones desde múltiples réplicas simultáneamente.

## 5. Health

```text
/health/live
/health/ready
```

Readiness verifica:

- DB;
- Redis opcional/obligatorio;
- storage config;
- configuración runtime.

No llamar OpenRouter en cada health check.

## 6. Cookies

Producción cross-site:

```text
Secure
HttpOnly
SameSite=None
```

Más:

- exact CORS;
- CSRF;
- HTTPS;
- trusted hosts;
- rotación de sesión.

Preferir subdominios del mismo dominio.

## 7. Backups

Supabase Free no incluye las mismas garantías de backups automáticos que planes pagos.

Para beta:

- export programado de PostgreSQL;
- prueba de restauración;
- inventario de objetos Storage;
- política de retención.

La imagen backend instala `postgresql-client` para que `scripts/backup.py` y
`scripts/restore_drill.py` puedan ejecutarse como release/cron commands. El
cliente no sustituye un backup administrado ni una restauración probada.

No afirmar “backup listo” hasta restaurarlo.

## 8. Checklist de una nueva máquina

- Clonar.
- Copiar `.env.example`.
- Instalar Python/Node declarados.
- `npm ci`.
- requirements dev.
- levantar Postgres test;
- migrar;
- tests;
- build;
- ejecutar servicios.

El CI existente debe seguir siendo la referencia de validación.
