# Guía de Despliegue en Netlify

Esta guía explica la solución al error `Cannot find module 'next/dist/server/lib/start-server.js'` y los pasos para desplegar **HiTrendy Web** de forma segura y exitosa en Netlify.

---

## Causas de los Errores

### 1. `Cannot find module 'next/dist/server/lib/start-server.js'`
Ocurre cuando el runtime de Netlify (`.netlify/dist/run/next.cjs`) en AWS Lambda (`/var/task`) no encuentra el paquete `next` debido a la estructura monorepo y el hoisting de dependencias.

### 2. `Cannot find module 'styled-jsx/package.json'`
```text
Error - Cannot find module 'styled-jsx/package.json'
Require stack:
- /var/task/node_modules/next/dist/server/require-hook.js
- /var/task/node_modules/next/dist/server/next.js
- /var/task/node_modules/next/dist/server/lib/start-server.js
- /var/task/.netlify/dist/run/next.cjs
```
Ocurre porque:
1. `next` requiere `styled-jsx` en su inicio mediante `require-hook.js:38` (`resolve('styled-jsx/package.json')`).
2. Al configurar `included_files = ["node_modules/next/**"]` en `netlify.toml`, el empaquetador de Netlify Functions excluye explícitamente `styled-jsx` y otras dependencias esenciales no anidadas dentro de `next/**`.
3. Al inicializarse la función serverless, la llamada a `resolve("styled-jsx/package.json")` falla porque `node_modules/styled-jsx` no fue copiado a `/var/task`.

---

## Solución Aplicada en el Código

1. **`netlify.toml` (Raíz) y `starter/web/netlify.toml`**:
   - Se ampliaron los `included_files` de Netlify Functions para incluir explícitamente `styled-jsx/**`, `next/**`, `@next/**`, `@swc/**`, `react/**` y `react-dom/**`.
2. **`package.json` (Raíz y `starter/web`)**:
   - Se declararon explícitamente `"styled-jsx": "5.1.1"`, `"react": "18.3.1"` y `"react-dom": "18.3.1"` para garantizar su presencia tanto a nivel raíz del monorepo como dentro de `starter/web`.
3. **`starter/web/next.config.js`**:
   - Se añadió `outputFileTracingRoot: path.join(__dirname, "../../")` para que el recolector de trazas de Next.js trace correctamente las dependencias desde la raíz del monorepo.

---

## Pasos para Desplegar en Netlify

### Opción 1: Despliegue Automático mediante GitHub (Recomendado)

1. Sube los cambios actuales a tu repositorio de GitHub:
   ```bash
   git add .
   git commit -m "fix(deploy): configuracion de netlify para monorepo next.js"
   git push origin main
   ```

2. Entra a tu panel de [Netlify](https://app.netlify.com).
3. Selecciona tu sitio existente (o haz clic en **Add new site** > **Import an existing project**).
4. Ve a **Site configuration** > **Build & deploy** > **Continuous deployment**:
   - **Base directory**: `starter/web` *(o déjalo en blanco si usas el `netlify.toml` de la raíz)*
   - **Build command**: `npm run build`
   - **Publish directory**: `.next`
5. En **Site configuration** > **Environment variables**, añade:
   - `NODE_VERSION`: `20`
   - `BACKEND_API_URL`: Tu API backend (ej. `https://hitrendy-api.onrender.com/api/v1` o la URL correspondiente).
6. **Muy Importante (Limpiar caché)**:
   - Ve a la pestaña **Deploys**.
   - Haz clic en **Trigger deploy** > **Clear cache and deploy site**.
   - Esto eliminará dependencias o artefactos desactualizados que causaban el fallo de `start-server.js`.

---

### Opción 2: Despliegue mediante Netlify CLI

Si prefieres desplegar directamente desde tu terminal:

1. Instala Netlify CLI globalmente si aún no lo tienes:
   ```bash
   npm install -g netlify-cli
   ```
2. Inicia sesión en Netlify:
   ```bash
   netlify login
   ```
3. Construye y despliega:
   ```bash
   npm run web:build
   netlify deploy --prod --dir=starter/web/.next
   ```

---

¡Listo! Tu aplicación Next.js ahora compilará y ejecutará sus rutas dinámicas y estáticas en Netlify sin fallos en las funciones serverless.