# Guía de Despliegue en Vercel y Render

Esta guía te permite publicar **HiTrendy** de forma permanente y gratuita en internet utilizando **Render** para el Backend y Base de Datos, y **Vercel** para el Frontend Web.

---

## Paso 1: Subir tus Cambios a GitHub

Asegúrate de que tu repositorio en GitHub tenga las configuraciones que preparamos:

```bash
git add .
git commit -m "chore(deploy): configuracion de produccion para Vercel y Render"
git push origin main
```

---

## Paso 2: Desplegar el Backend y Base de Datos en Render

1. Entra a [render.com](https://render.com) e inicia sesión con tu cuenta de GitHub.
2. En el Dashboard, haz clic en **New +** y selecciona **Blueprint**.
3. Conecta tu repositorio: `edwinjosuems12-wq/hi-trend`.
4. Render detectará automáticamente el archivo [`render.yaml`](file:///c:/Users/edwin/OneDrive/Escritorio/trendIA/Trend-AI/render.yaml) y te mostrará los dos recursos que creará:
   - **Base de Datos PostgreSQL**: `hitrendy-db` (Plan gratuito).
   - **Servicio Web API**: `hitrendy-api` (FastAPI con Python).
5. En los campos de variables de entorno que te solicite, completa:
   - `AI_API_KEY`: Tu API Key de Groq o proveedor de IA.
6. Haz clic en **Apply**.
7. Render creará la base de datos, ejecutará automáticamente las migraciones (`alembic upgrade head`) e iniciará la API.
8. Al terminar, copia la URL pública de tu API (ejemplo: `https://hitrendy-api.onrender.com`).

---

## Paso 3: Desplegar el Frontend en Vercel

1. Entra a [vercel.com](https://vercel.com) e inicia sesión con GitHub.
2. Haz clic en **Add New...** > **Project**.
3. Importa tu repositorio `hi-trend`.
4. En la pantalla de configuración del proyecto:
   - **Root Directory**: Haz clic en *Edit* y selecciona `starter/web`.
   - **Framework Preset**: Next.js (se detecta automáticamente).
5. Despliega la sección **Environment Variables** y añade:
   - **Nombre**: `BACKEND_API_URL`
   - **Valor**: `https://hitrendy-api.onrender.com/api/v1` *(usa la URL real de tu backend en Render agregando `/api/v1` al final)*.
6. Haz clic en **Deploy**.
7. Vercel compilará la aplicación en ~1 minuto y te dará tu dominio público oficial (ejemplo: `https://hitrendy.vercel.app` o tu dominio personalizado).

---

## Paso 4: Vincular el Dominio de Vercel en Render

La URL actual de Vercel es `https://hi-trend-web.vercel.app`:

1. Ve a tu servicio `hitrendy-api` en [Render Dashboard](https://dashboard.render.com).
2. Ve a la pestaña **Environment**.
3. Configura o añade:
   - `FRONTEND_URL`: `https://hi-trend-web.vercel.app`
   - `ALLOWED_ORIGINS`: `https://hi-trend-web.vercel.app`
4. Guarda los cambios para que se reinicie el servicio.

---

## Paso 5 (Opcional): Activar Inicio de Sesión con Google

Para que el botón **"Continuar con Google"** funcione con tu nuevo dominio de Vercel:

1. Abre tu [Google Cloud Console > Credenciales](https://console.cloud.google.com/apis/credentials).
2. Selecciona tu ID de cliente OAuth 2.0.
3. En **Orígenes de JavaScript autorizados**, añade:
   ```text
   https://hi-trend-web.vercel.app
   ```
4. En **URIs de redireccionamiento autorizados**, añade:
   ```text
   https://hi-trend-web.vercel.app/api/v1/auth/google/callback
   ```
5. En Render, asegúrate de tener la variable:
   - `GOOGLE_REDIRECT_URI`: `https://hi-trend-web.vercel.app/api/v1/auth/google/callback`

---

¡Listo! Con esto tendrás tu plataforma 100% funcional en producción, disponible las 24 horas del día, con base de datos en la nube y dominio seguro HTTPS.
