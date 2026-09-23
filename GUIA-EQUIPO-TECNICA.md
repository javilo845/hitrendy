# HiTrendy — Guía técnica del proyecto

**Para:** los 6 integrantes del grupo.
**Cómo usarla:** las secciones 1 a 5 y la 10 son de lectura obligatoria para todos —
son las preguntas que cualquiera puede recibir. Después, cada quien profundiza en
la sección de su área (6, 7, 8 o 9).

**Regla de oro para exponer:** si te preguntan algo que no es de tu área, no
improvises. Explica el principio general (sección 4) y pasa la palabra a quien
llevó esa parte. Un equipo que sabe delegar la pregunta se ve mejor que uno donde
todos contestan a medias.

---

## 1. Qué es HiTrendy

Un asistente web para que un negocio pequeño produzca contenido para redes
sociales. No es un chat genérico: cada texto que genera usa el perfil del
negocio, su identidad de marca, el objetivo de la campaña y la plataforma
destino.

El flujo central es:

1. El usuario se registra y hace un **onboarding** de 4 pasos donde describe su
   negocio (nombre, categoría, país, producto, público) y su marca (tono, colores,
   propuesta de valor).
2. Pide algo: un post, un reel, una campaña, una reescritura.
3. El sistema **inyecta el perfil y las reglas de marca** en el prompt.
4. Un modelo de lenguaje devuelve un resultado **estructurado y editable** —no
   texto libre, sino un contrato con campos definidos (hook, caption, hashtags,
   call to action, dirección visual).
5. El usuario lo edita y lo guarda como **proyecto**, con versiones.

**Lo que deliberadamente NO hace en esta versión** (esto lo pueden preguntar, y la
respuesta correcta es que fue una decisión, no una carencia):

- No publica automáticamente en las redes.
- No hace scraping masivo de TikTok/Instagram/X.
- No entrena un modelo propio ni hace fine-tuning con datos del usuario.
- No es un editor libre tipo Canva.
- No es un dashboard complejo de analítica de tendencias.

La condición de éxito del MVP está escrita en el README: *un usuario nuevo
completa el onboarding, pide un post, recibe un resultado personalizado, lo
edita y lo guarda como proyecto en menos de cinco minutos.*

---

## 2. Cómo se levanta el proyecto

Requisitos: **Python 3.12** y **Node.js 20**.

```bash
# 1. Preparar entorno
python3.12 -m venv .venv
source .venv/bin/activate
cp .env.example .env
python -m pip install -r starter/backend/requirements-dev.txt
npm ci

# 2. Servicios de apoyo (opcionales en modo demo)
docker compose up -d postgres redis minio

# 3. Backend: migraciones + servidor en el puerto 8000
npm run backend:dev

# 4. Frontend en el puerto 3000 (otra terminal)
npm run web:dev

# Todo junto (web + backend + worker de imágenes)
npm run dev
```

El frontend **no llama al backend por URL absoluta**. En `next.config.js` hay un
rewrite: `/api/v1/:path*` → `http://127.0.0.1:8000/api/v1/:path*`. Por eso el
navegador siempre ve un mismo origen y las cookies de sesión funcionan sin CORS
en desarrollo.

### Puertos: por qué 8000 y 3000 no son intercambiables

Google tiene registrado `http://localhost:8000/api/v1/auth/google/callback` como
URI de redirección, y tras el callback el backend devuelve el navegador a
`FRONTEND_URL` (puerto 3000). Ese par es el único donde el login con Google
termina de principio a fin. Con el backend en otro puerto, Google manda al
usuario a un puerto donde no escucha nadie y el navegador muestra una conexión
rechazada.

Por eso `npm run dev` resuelve los dos puertos antes de arrancar nada, en
`scripts/dev.mjs`, y se los pasa a los tres procesos. Al encontrar un puerto
ocupado distingue de quién es:

- **Un proceso de este repositorio** (un `next dev` o un `uvicorn` que quedó
  colgado de una ejecución anterior, identificado por su directorio de trabajo y
  su línea de comandos) se termina y el puerto se reclama. Es la única forma de
  no ir derivando a 8001, 8002, 8003 cada vez que una sesión muere mal.
- **Cualquier otra cosa** —el servidor de otro proyecto, un contenedor— no se
  toca. Se pasa al siguiente puerto libre y se avisa, en el arranque, de que el
  login con Google no va a funcionar ahí.

En ese caso el resto de la aplicación sigue siendo coherente: `dev.mjs` propaga
`NEXT_PUBLIC_API_URL`, `FRONTEND_URL`, `GOOGLE_REDIRECT_URI` y añade el nuevo
origen a `ALLOWED_ORIGINS` (sin lo cual el backend se niega a arrancar, ver
`app/core/config.py`). Para recuperar el login con Google hay que liberar el
8000 y el 3000, o registrar los puertos nuevos en Google Cloud Console.

`npm run backend:dev` y `npm run web:dev` por separado hacen lo mismo con su
propio puerto, y avisan si acaban fuera del canónico.

Validación rápida, sin credenciales externas ni backend corriendo:

```bash
npm run validate        # lint + typecheck + tests
npm run validate:e2e    # migraciones y E2E contra PostgreSQL
```

---

## 3. Mapa del repositorio

```text
hi-trend/
├── docs/                  Documentación viva: producto, marca, UX, arquitectura,
│                          IA, API, implementación, demo, plan de beta
├── contracts/schemas/     Los contratos JSON Schema (fuente de verdad)
├── design/                Tokens de diseño exportados (css, json) + preview
├── references/figma/      Capturas y referencias visuales originales
├── starter/backend/       API FastAPI, dominio, providers, migraciones, pruebas
├── starter/web/           App Next.js (App Router), componentes, cliente API, pruebas
├── scripts/               Validación, backup, restore drill, chequeos de beta
├── demo/                  Demo offline mínima (ilustra el producto, no es la arquitectura)
└── project-manifest.yaml  Manifiesto: contextos acotados y fuentes de verdad
```

**Jerarquía de fuente de verdad** (cuando dos documentos se contradicen):

1. `contracts/schemas/`
2. ADRs aceptados en `docs/03-architecture/adr/`
3. `docs/06-implementation/agentic-playbook.md`
4. El resto de `docs/`
5. El código
6. La demo

---

## 4. Las seis reglas de arquitectura

Estas seis reglas son el corazón del proyecto. **Cualquiera del equipo debe poder
explicar las seis.** Son lo que diferencia esto de un proyecto de clase.

### 4.1. Contract-first

Antes que el código están los contratos: `contracts/schemas/*.json` define qué es
un `template`, un `business-profile`, un `generated-social-post`, un
`short-video-script`, un `brand-profile`, un `chat-request` y un
`asset-analysis`. El backend valida contra ellos y el frontend tipa contra ellos.

Consecuencia práctica: cuando el modelo de IA devuelve algo que no cumple el
contrato, la petición **falla con `GENERATION_CONTRACT_INVALID`** en lugar de
mostrarle basura al usuario.

### 4.2. Dirección de dependencias

```
UI  →  servicio de aplicación  →  dominio  →  interfaz de provider  →  modelo/almacenamiento externo
```

La flecha nunca se invierte. El dominio no importa React, ni FastAPI, ni el SDK de
OpenAI, ni boto3. Los datos específicos de un proveedor **se quedan en el borde**:
se traducen en el adaptador y hacia adentro solo viaja el contrato.

Por qué importa: cambiar de OpenAI a OpenRouter no toca ni una línea de dominio.

### 4.3. Providers intercambiables y modo demo

Cada capacidad externa tiene una interfaz y varias implementaciones,
seleccionadas por variable de entorno:

| Capacidad | Variable | Valores |
|---|---|---|
| Texto/LLM | `AI_PROVIDER` | `demo`, `openai-compatible`, `openrouter` |
| Imágenes | `IMAGE_PROVIDER` | `demo`, `openai`, `openrouter`, `replicate` |
| Video | `VIDEO_PROVIDER` | `demo`, `openai` |
| Visión (crítica visual) | `VISION_PROVIDER` | `demo`, `openai-compatible` |
| Almacenamiento | `OBJECT_STORAGE_PROVIDER` | `local`, `s3`, `supabase`, `disabled` |
| Cache/rate limit | `REDIS_PROVIDER` | `disabled`, `memory`, `redis` |
| Email | `EMAIL_PROVIDER` | `disabled`, `demo`, `resend` |

Con todo en `demo` el proyecto **corre completo sin una sola credencial**. Eso es
lo que permite que cualquiera clone el repo y lo vea funcionando, y lo que permite
que el CI pase sin secretos.

Protección incluida: `app/core/config.py` valida la configuración al arrancar y
**se niega a levantar en producción con providers demo**. Un `demo` en producción
lanza `GENERATION_PROVIDER_UNAVAILABLE` (503) en vez de fingir que funciona.

### 4.4. Todo el texto visible va en español

Los identificadores técnicos (nombres de variables, códigos de error, claves de
API) van en inglés. Todo lo que ve el usuario va en español. La app además soporta
**es / en / pt** desde `starter/web/lib/i18n.ts`.

### 4.5. Sobre de error uniforme

Todos los errores de la API salen con la misma forma:

```json
{ "error": { "code": "RATE_LIMITED", "message": "Demasiadas solicitudes...", "retryable": true } }
```

El frontend tiene una clase `ApiError` que lee ese sobre. El campo `retryable` le
dice a la interfaz si tiene sentido ofrecer "Reintentar".

### 4.6. Datos sensibles

Nunca se registran en logs secretos, tokens ni contenido privado innecesario. Las
áreas tratadas como alto riesgo son: autenticación, datos de usuario, prompts,
contenido generado, exportaciones, borrados, migraciones y payloads de providers.

---

## 5. Recorrido end-to-end (lo que se demuestra)

Este es el guion de la demostración. Vale la pena que los tres de programación lo
puedan narrar completo.

1. **Landing** (`/`) — pública, sin sesión. Solo dos acciones: conocer el producto
   y empezar a crear.
2. **Registro** (`/register`) — crea un *pending signup*. El registro es
   **persistente en el servidor**: si el usuario cierra el navegador a mitad del
   onboarding, al volver retoma donde iba (tabla `pending_signups`, migración 014).
3. **Onboarding** (`/onboarding`) — 4 pasos: negocio → canales y objetivos →
   identidad de marca → revisión. Cada paso guarda un draft en el servidor
   (`PATCH /auth/signup`), no en el navegador.
4. **Dashboard** (`/dashboard`) — proyectos activos/archivados, buscador, y la
   sección "Recomendadas" con el carrusel de plantillas sugeridas por IA.
5. **Plantillas** (`/templates`) — catálogo completo en rejilla, con filtro por
   búsqueda y por categoría (Reels, Posts, Stories, Anuncios).
6. **Studio** (`/studio/new`, `/studio/[conversationId]`) — la conversación donde
   se pide el contenido. Devuelve tarjetas de artefacto editables.
7. **Proyecto** (`/projects/[id]`) — el resultado guardado, con historial de
   versiones y opción de restaurar.
8. **Ajustes** (`/settings`) — perfil de negocio, marca, idioma de interfaz,
   conexiones sociales, uso de IA y borrado de cuenta.

Hay 21 páginas en total; las anteriores son las que importan para la demo.

---

## 6. Área de Ewin — núcleo de la aplicación

> Desarrollo principal: dominio, servicios de generación, conversaciones,
> proyectos, modelo de datos y migraciones.

### 6.1. Qué construiste

El backend está partido en **contextos acotados** (declarados en
`project-manifest.yaml`), cada uno dueño de sus tablas:

| Contexto | Es dueño de |
|---|---|
| `identity` | usuarios, sesiones, workspaces |
| `business_profile` | negocios, audiencias, perfiles de marca, objetivos |
| `conversation` | hilos, mensajes, adjuntos |
| `generation` | trabajos de generación, artefactos generados, llamadas a provider |
| `templates` | plantillas, etiquetas, recomendaciones |
| `library` | assets, carpetas, proyectos |
| `analytics` | eventos, feedback, métricas de uso |

Un contexto no escribe en las tablas de otro: pasa por su repositorio.

### 6.2. Funciones y módulos que debes poder explicar

**Servicios de generación** (`app/services/`):

- `generate_social_post.py` — arma el prompt con el perfil del negocio y la marca,
  llama al provider de contenido y **valida la respuesta contra el contrato**
  `generated-social-post.schema.json`. Si no valida, error explícito.
- `generate_short_video_script.py` — igual, pero produce guion de video corto.
- `generate_advice.py` — el "asesor": responde con recomendaciones sobre el
  contenido en vez de generar una pieza.
- `usage_policy.py` y `ai_usage.py` — cuánto puede consumir cada workspace y el
  registro de ese consumo (migración 016, `ai_usage_events`).

**Contrato y evaluación** (`app/generation/`):

- `contracts.py` — la forma exacta que debe tener lo que devuelve el modelo.
- `prompt_registry.py` — los prompts versionados, no dispersos por el código.
- `evaluation.py` / `model_evaluation.py` — cómo se mide si una salida es buena.

**Conversaciones** (`app/conversations/`):

- `routes.py` expone 8 endpoints: crear/listar/leer conversación, enviar mensaje,
  generar variaciones de un artefacto, y registrar feedback y eventos.
- `idempotency.py` — **esta es la joya de tu parte**. Enviar un mensaje cuesta
  dinero (llama al modelo). Si el usuario tiene mala señal y el navegador
  reintenta, no se puede generar dos veces. Cada petición trae una cabecera
  `Idempotency-Key`; el servidor guarda una huella del payload
  (`payload_fingerprint`) y una fila de reserva. Funciones: `reserve()`,
  `complete()`, `mark_failed()`, `recover_failed()`. Si llega la misma clave con
  el mismo payload, se devuelve el resultado anterior; si llega con un payload
  distinto, es un `ConflictError`.

**Proyectos** (`app/projects/routes.py`, 11 endpoints): crear desde plantilla,
listar, leer, actualizar, **duplicar**, **exportar**, guardar versión de artefacto,
listar versiones y **restaurar una versión**. El historial de versiones es lo que
convierte un resultado de IA en algo con lo que se puede trabajar de verdad.

**Modelo de datos**: 26 migraciones Alembic, de `001_initial` a
`026_repair_template_public_flag`. Las que conviene mencionar:
`011_idempotency_records`, `014_pending_signups_onboarding`,
`016_ai_usage_events`, `022_image_generation_jobs`, `024_video_generation`.

### 6.3. Preguntas que te pueden hacer

- *"¿Qué pasa si el modelo devuelve algo raro?"* → Se valida contra el contrato;
  si no cumple, la petición falla con un código de error explícito. Nunca se
  guarda una salida inválida.
- *"¿Y si el usuario da doble clic en generar?"* → Idempotencia por
  `Idempotency-Key` con huella del payload.
- *"¿Cómo se cambia el modelo de IA?"* → Es una variable de entorno; el dominio no
  se entera.

---

## 7. Área de Edware — APIs, providers y configuración

> Configuración del sistema, superficie HTTP, adaptadores de proveedores externos,
> seguridad de transporte y despliegue.

### 7.1. Qué construiste

La API expone **unos 80 endpoints bajo `/api/v1`**, repartidos en 12 routers:

| Router | Prefijo | Endpoints | Qué hace |
|---|---|---|---|
| identity | `/auth` | 19 | registro, login, logout, `me`, signup persistente, Google OAuth, reset de contraseña, CSRF, uso, borrado de cuenta |
| projects | `/projects` | 11 | proyectos, versiones, duplicado, exportación, eventos de flujo |
| conversations | `/conversations` | 8 | hilos, mensajes, variaciones, feedback |
| business | `/businesses` | 7 | negocio, perfil de marca, asesor |
| assets | `/assets` | 6 | subidas en dos fases, contenido, análisis |
| images | `/images` | 6 | brief, preflight, jobs, archivos |
| videos | `/videos` | 6 | storyboard, preflight, jobs, archivos |
| trends | `/trends` | 5 | home, listado, detalle, fuentes, refresh |
| social | `/social` | 5 | conexiones, autorización OAuth, callback, verificación, desconexión |
| templates | `/templates` | 3 | listar, detalle, **recomendaciones** |
| operations | (raíz) | 3 | políticas, feedback, reportes de abuso |
| capabilities | `/capabilities` | 1 | qué puede hacer el sistema con la config actual |

### 7.2. Middleware y controles (todo en `app/main.py`)

Este es el corazón de tu parte; se ejecuta en cada petición:

1. **Trusted host** — solo se responde a los hosts declarados.
2. **Rate limiting** — sobre las rutas caras y sensibles: login, registro,
   `signup/start`, `signup/complete`, Google OAuth, reset de contraseña, y
   cualquier ruta que termine en `/messages`, `/advisor`, `/variations`,
   `/analyses`, `/feedback`, `/abuse/reports` o `/authorize`. Devuelve **429** con
   cabecera `Retry-After`.
3. **Límite de tamaño de cuerpo** — `413 REQUEST_TOO_LARGE` si excede
   `MAX_REQUEST_BODY_BYTES`; `400 INVALID_CONTENT_LENGTH` si el `Content-Length`
   viene corrupto.
4. **CORS** con lista explícita de cabeceras permitidas: `Content-Type`,
   `Authorization`, `X-CSRF-Token`, `X-Request-Id`, `Idempotency-Key` y
   `X-Deletion-Status-Token`.
5. **Request ID** — cada petición lleva un identificador que viaja en logs y en la
   respuesta, para poder rastrear un incidente.
6. **Métricas** — se registra código de estado y duración de cada petición.

### 7.3. Configuración (`app/core/config.py`)

Más de mil líneas, y la parte importante es `validate_runtime_configuration()`:
se ejecuta al arrancar y **rechaza combinaciones peligrosas**. Ejemplos reales que
puedes citar:

- `EMAIL_PROVIDER=demo` está prohibido en staging y producción.
- `VIDEO_GENERATION_ENABLED=1` con `VIDEO_PROVIDER=demo` es un error de arranque.
- El modelo rápido de OpenRouter **debe** ser `openrouter/free`: es la única ruta
  garantizada gratuita, y el código lo verifica en el propio factory para que
  nadie active gasto por accidente.
- Si `REDIS_PROVIDER=redis`, tiene que haber `REDIS_URL`.

La filosofía: **fallar al arrancar es barato; fallar en producción no**.

### 7.4. El factory de providers (`app/providers/factory.py`)

Es el punto único donde se decide qué implementación se usa. Recibe un
`QualityLevel` (`FAST`, `BALANCED`, `QUALITY`) y devuelve el adaptador
correspondiente. Si falta configuración, lanza `GENERATION_PROVIDER_UNAVAILABLE`
(503) en vez de reventar con un stack trace.

Detalle técnico que vale mencionar: para los providers compatibles con OpenAI se
activa **structured output** (decodificación restringida por esquema). Sin eso el
modelo inventa la forma de la respuesta y la validación de contrato falla; con eso
el modelo está obligado a producir el contrato.

### 7.5. Seguridad de credenciales

- Contraseñas: `app/identity/passwords.py`.
- Sesión por cookie + **CSRF** (`app/core/csrf.py`, `app/core/cookies.py`).
- Tokens de redes sociales: `app/social/crypto.py` los guarda cifrados con
  **AES-256-GCM versionado** (`v1`). La base de datos se trata como
  almacenamiento no confiable: el texto plano solo existe dentro de la petición
  que está a punto de entregárselo al proveedor. Por eso `cryptography` es
  dependencia directa y no heredada de otro paquete.

### 7.6. Despliegue y operación

- `docker-compose.yml` levanta postgres, redis y minio.
- CI en `.github/workflows/ci.yml`, con **tres jobs separados**: backend rápido
  (ruff + pytest), PostgreSQL/migraciones/E2E, y frontend (tests, typecheck,
  lint). El CI corre **sin secretos**, usando providers demo.
- `scripts/backup.py`, `scripts/restore_drill.py` — respaldo y simulacro de
  restauración; `scripts/beta_readiness_check.py` — chequeo previo a beta.
- Workers separados del servidor web: `python -m app.images.worker` y el
  equivalente de video.

---

## 8. Área de Roberto — frontend e integración

> Interfaz Next.js, cliente de API, integración con el backend junto a Ewin,
> estados de carga y degradación.

### 8.1. Base técnica

**Next.js 14.2.5 con App Router**, React 18.3.1, TypeScript. **Sin framework CSS**:
nada de Tailwind ni Bootstrap. Toda la interfaz se construye sobre un sistema de
tokens propio (`app/tokens.css`) y una hoja global (`app/globals.css`).

Dependencias de producción, en total: `next`, `react`, `react-dom`, `zod`,
`animejs` y `animate.css`. Esa lista corta es una decisión: menos superficie, menos
peso, menos cosas que se rompen.

### 8.2. El cliente de API (`lib/api.ts`)

Un solo archivo concentra **toda** la comunicación con el backend, organizado por
recurso: `api.auth`, `api.businesses`, `api.templates`, `api.projects`,
`api.conversations`, `api.artifacts`, `api.assets`, `api.images`, `api.videos`,
`api.trends`, `api.social`, `api.capabilities`, `api.operations`.

Ningún componente hace `fetch` por su cuenta. Ventaja: el manejo de CSRF, de
cookies (`credentials: "include"`), de reintentos y del sobre de error está en un
solo lugar. Si mañana cambia la forma del error, se cambia una vez.

Además exporta la clase `ApiError`, que lleva el `status` y el `code` del backend,
y es lo que permite distinguir "no hay sesión" (401) de "el servidor se cayó".

### 8.3. Integraciones que hiciste

**Carrusel de plantillas recomendadas** — `components/templates/template-carousel.tsx`

La decisión técnica: **scroll-snap nativo**, no una animación con `requestAnimationFrame`
ni una librería de carrusel. Es decir `overflow-x: auto` +
`scroll-snap-type: x mandatory` en la pista, `scroll-snap-align: start` en cada
tarjeta, y las flechas hacen `track.scrollBy({ left: paso })`.

Por qué es la forma correcta:

- El deslizamiento con el dedo en móvil lo hace el navegador, no nuestro código.
- La accesibilidad por teclado sale gratis: cada tarjeta tiene un botón enfocable,
  y el navegador hace scroll al foco por sí solo.
- El paso se calcula midiendo la primera tarjeta y el `gap` real del CSS, así que
  si el diseño cambia el ancho de la tarjeta, el carrusel se ajusta solo.
- Un `useEffect` escucha `scroll` y `resize` para deshabilitar la flecha izquierda
  al principio y la derecha al final (`atStart` / `atEnd`).
- Respeta `prefers-reduced-motion`: si el usuario pidió menos animación, el scroll
  es instantáneo en vez de suave.

**Recomendaciones de IA** — `lib/template-recommendations.ts`

Conecta el endpoint `POST /api/v1/templates/recommendations`, que puntúa cada
plantilla (plataforma coincidente +3, objetivo +2, categoría +1) y devuelve un
`score` y una `rationale` en español que se muestra como "Por qué: ...".

Dos detalles que demuestran cuidado:

- La función **lee el perfil del negocio primero** (`readBusinessTargeting`) para
  saber plataforma y objetivo. Si el negocio no los tiene configurados, ni siquiera
  hace la llamada.
- Pide `limit: 6` porque el backend valida `ge=1, le=6`. Pedir 7 devolvería un 422
  y el usuario vería el catálogo plano sin enterarse de que la función falló.

**Portadas del hero** — El riel superior del dashboard ya no muestra tres imágenes
fijas: toma las portadas reales del catálogo. Las tres imágenes originales quedan
como respaldo para que la página no salte cuando la API todavía no respondió.

**Arreglo del login** — `components/auth/public-auth-route.tsx`

El problema: la aplicación se quedaba trabada en el login. Dos causas:

1. La guarda de rutas públicas trataba *cualquier* fallo de `GET /auth/me` como
   "hay que esperar". Si el backend no respondía, el usuario se quedaba viendo el
   splash para siempre. La corrección: **solo un 401 limpio es información**;
   cualquier otro error hace *fail open* y muestra el formulario. Una página que no
   protege nada no debe poder atrapar a nadie.
2. Un registro sin terminar redirigía a `/onboarding`. La cookie de signup dura un
   día, así que quien abandonaba un registro quedaba bloqueado del login 24 horas.
   La corrección: la ruta acepta un modo (`resume` o `notice`). `/register` sigue
   redirigiendo; el login y el reset de contraseña solo muestran un aviso
   "Tienes un registro sin terminar / Continuar registro". **Un borrador es una
   oferta, no un desvío.**

**Otras integraciones del frontend:** exportación del plan a PDF
(`lib/plan-export.ts`), enlaces a Canva segmentados por nicho
(`lib/canva-templates.ts`), flujo de publicación en Instagram
(`lib/instagram-flow-copy.ts`), generación de imágenes y de video con seguimiento
de trabajos (`lib/image-generation.ts`), y el módulo de tendencias
(`lib/trends-copy.ts`).

### 8.4. Internacionalización

`lib/i18n.ts` centraliza los textos en **español, inglés y portugués**, separados en
`appCopy` (textos de página) y `surfaceCopy` (textos de componentes reutilizables).
Los componentes reciben el copy por props; no lo buscan por su cuenta. Eso es lo
que permite probarlos en aislamiento.

### 8.5. Preguntas que te pueden hacer

- *"¿Por qué no usaron una librería de carrusel?"* → Porque el navegador ya lo hace
  mejor: scroll-snap nativo da gestos táctiles, accesibilidad y rendimiento sin
  agregar peso al bundle.
- *"¿Qué pasa si la API de recomendaciones falla?"* → Se muestra el catálogo. La
  sección nunca queda vacía. (Ver sección 10.)
- *"¿Por qué un solo archivo de API?"* → Un solo punto para CSRF, cookies, errores
  y reintentos.

---

## 9. Área de diseño gráfico (3 integrantes)

> Ustedes ya saben lo que hicieron. Esta sección es para conectar su trabajo con
> el código, que es la pregunta que probablemente reciban.

### 9.1. Dónde vive su trabajo dentro del repositorio

| Qué | Dónde |
|---|---|
| Referencias originales de Figma | `references/figma/` |
| Sistema de marca escrito | `docs/01-brand/brand-system.md` |
| Voz y tono del contenido | `docs/01-brand/content-voice.md` |
| Accesibilidad | `docs/01-brand/accessibility.md` |
| Tokens documentados | `docs/01-brand/design-tokens.md` |
| Tokens exportados | `design/tokens.css`, `design/tokens.json` |
| Tokens implementados | `starter/web/app/tokens.css` |
| Especificación de pantallas | `docs/02-ux/screen-specs.md` |
| Contratos de componentes | `docs/02-ux/component-contracts.md` |
| Estados y textos | `docs/02-ux/states-and-copy.md` |
| Auditoría contra Figma | `docs/02-ux/figma-audit.md` |

### 9.2. Cómo se traduce el diseño a código: los tokens

Esta es **la idea que hay que saber explicar**. El archivo
`starter/web/app/tokens.css` tiene cinco capas, en orden de dependencia, y cada
capa solo puede mirar hacia arriba:

1. **Paleta de marca** — los únicos valores de color literales de todo el proyecto:
   `--ht-navy: #1e1a5e`, `--ht-purple: #7c3aed`, `--ht-pink: #f472e0`,
   `--ht-paper: #f6f4ff`, etc.
2. **Rampa derivada** — mezclas de la capa 1 para superficies que la paleta implica.
3. **Roles semánticos** — `--background`, `--foreground`, `--primary`, `--border`.
4. **Roles de superficie** — landing, auth, onboarding, shell de la app, chat del studio.
5. **Tokens de componente** — radios, sombras, tipografía, elevación, movimiento.

**La regla que hace que esto funcione:** ningún componente escribe un color a
mano. Si una superficie nueva necesita un color, primero se le da un rol en los
tokens, y el componente usa ese rol.

Consecuencia: cambiar la marca entera es editar la capa 1. Y también significa que
un desarrollador **no puede** romper el Figma sin darse cuenta, porque no tiene
literales que tocar.

### 9.3. Ejemplo concreto: el carrusel nuevo

El carrusel agregado al dashboard usa solo tokens existentes:
`var(--ht-white)` para el fondo de la tarjeta, `var(--border)` para el borde,
`var(--shadow-soft)` para la sombra, `var(--primary)` para el botón, y
`var(--radius-pill)` para su forma. Cero colores nuevos. Por eso encaja
visualmente sin necesidad de revisar el Figma otra vez.

Las proporciones de las miniaturas también vienen del diseño: `4 / 5` para posts y
anuncios, `9 / 16` para reels y stories, declaradas en `lib/template-catalog.ts`.

### 9.4. Accesibilidad

Hay pruebas automáticas de accesibilidad en el frontend (`vitest-axe`), y el
sistema respeta `prefers-reduced-motion` en las animaciones. El contraste de la
paleta está documentado en `docs/01-brand/accessibility.md`.

---

## 10. Fallbacks: qué pasa cuando algo falla

Esta sección es la que más impresiona en una defensa, porque la mayoría de los
proyectos no la tiene. **Todos deberían poder citar al menos tres de estos.**

El principio general: **una falla en una función secundaria nunca puede romper la
pantalla completa.** Se degrada, no se cae.

| Situación | Comportamiento | Dónde |
|---|---|---|
| El endpoint de recomendaciones falla, devuelve vacío, o el negocio no tiene plataforma/objetivo | Se muestra el catálogo normal recortado. La función `loadRecommendedTemplates` **nunca lanza excepción** | `lib/template-recommendations.ts` |
| El perfil del negocio no se puede leer | Se sigue adelante sin segmentación, con el catálogo | `app/dashboard/page.tsx` |
| El catálogo todavía no responde | El riel del hero muestra las tres portadas incluidas en el proyecto, sin salto de layout | `app/dashboard/page.tsx` |
| Una miniatura no carga | `onError` cambia a un marcador visual con el mismo tamaño | `template-carousel.tsx` |
| Una plantilla nueva sin metadatos de presentación | `fallbackMeta`: categoría "Posts", proporción 4/5, sin etiquetas | `lib/template-catalog.ts` |
| `GET /auth/me` falla por algo que no sea 401 | *Fail open*: se muestra el formulario en vez de dejar al usuario atrapado | `components/auth/public-auth-route.tsx` |
| Registro sin terminar en el login | Aviso con enlace para continuar, sin redirección forzada | `components/auth/public-auth-route.tsx` |
| No hay credenciales de IA configuradas | Providers demo: la app corre completa, offline | `app/providers/factory.py` |
| Provider demo en producción | Se rechaza con 503 explícito, no se finge que funciona | `app/providers/factory.py` |
| No hay Redis | Limitador de peticiones **en memoria del proceso** en vez de compartido | `app/main.py`, `app/core/rate_limit.py` |
| No hay S3 | Almacenamiento en disco local | `app/providers/storage.py` |
| Una fuente de tendencias se cae o agota su cuota | Se sirve el resultado cacheado y se registra el `next_reset_at` de la cuota | `app/trends/cache.py`, `app/trends/service.py` |
| Dos peticiones idénticas de tendencias a la vez | `coalesce`: una sola llamada real, ambas reciben el mismo resultado | `app/trends/cache.py` |
| El usuario reintenta un mensaje ya enviado | Idempotencia: se devuelve el resultado anterior, no se paga dos veces | `app/conversations/idempotency.py` |
| Dos workers toman el mismo trabajo de imagen | `SELECT ... FOR UPDATE SKIP LOCKED`: nunca se genera dos veces | `app/images/worker.py` |
| Dos confirmaciones concurrentes agotan el presupuesto | Reserva con fila bloqueada + restricción `consumed <= budget` en la base | `app/images/budget.py` |
| Un trabajo falla **antes** de llamar al proveedor | Se libera la reserva de presupuesto |  `app/images/budget.py` |
| Un trabajo falla **después** de llamar al proveedor | El gasto se mantiene consumido, porque ya se pagó | `app/images/budget.py` |
| El almacenamiento del navegador no está disponible en modo demo | La pantalla actual sigue funcionando | `lib/demo-mode.ts` |

---

## 11. Integraciones externas

| Integración | Módulo | Notas |
|---|---|---|
| Modelos de texto compatibles con OpenAI | `app/providers/content.py` | Structured output activado para forzar el contrato |
| OpenRouter | `app/providers/openrouter_catalog.py` | Tres niveles de calidad; el nivel rápido está fijado a `openrouter/free` |
| Generación de imágenes | `app/providers/images.py` + `app/images/` | Trabajos durables, worker separado, presupuesto diario por workspace |
| Generación de video | `app/providers/video.py` + `app/videos/` | Storyboard, preflight, jobs; duraciones demo de 5 y 10 s |
| Visión / crítica visual | `app/providers/vision.py` | Analiza un asset subido y devuelve observaciones |
| Google OAuth (inicio de sesión) | `app/identity/google_oauth.py` | `start` / `callback` con `state`, `nonce` y PKCE; el ID token se valida contra las claves públicas de Google |
| Conexiones sociales (Instagram) | `app/social/` | OAuth con estado (`oauth_state.py`) y tokens cifrados AES-GCM |
| Almacenamiento de objetos | `app/providers/storage.py` | local / S3 / Supabase |
| Redis o Upstash | `app/core/ephemeral_store.py` | Cache, estado efímero y rate limiting compartido |
| Email transaccional (Resend) | `app/operations/email.py` | Adaptador; `demo` prohibido fuera de desarrollo |
| Canva | `starter/web/lib/canva-templates.ts` | Enlaces de búsqueda segmentados por nicho del negocio |

**Patrón común a todas:** interfaz en el dominio → adaptador en el borde →
selección por variable de entorno → implementación demo siempre disponible.

---

## 12. Pruebas y validación

| Capa | Herramienta | Volumen |
|---|---|---|
| Backend | pytest (+ pytest-asyncio, aiosqlite) | más de 50 archivos de prueba |
| Backend lint | ruff | en CI |
| Frontend unitario | vitest + Testing Library + vitest-axe | 206 pruebas |
| Frontend tipos | `tsc --noEmit` | en CI |
| Frontend lint | ESLint (`next lint`) | en CI |
| Extremo a extremo | Playwright, dos perfiles: escritorio y móvil (Pixel 7) | 42 escenarios |
| Migraciones | pytest contra PostgreSQL real | job propio en CI |

Los tests del backend usan marcas (`markers`) para separar lo rápido de lo que
toca servicios reales: `e2e`, `real_ai`, `real_trends`, `real_images`,
`real_social`, `real_video`. El CI corre todo **menos** las marcas reales, por eso
no necesita ninguna credencial.

Comandos:

```bash
npm run validate        # todo lo rápido
npm run web:test        # solo frontend
npm run backend:test    # solo backend
npm run web:test:e2e    # Playwright
```

---

## 13. Estado actual y pendientes conocidos

Ser honesto sobre lo pendiente es mejor que fingir que no existe. Si preguntan,
esta es la respuesta:

- **Lo que funciona:** typecheck limpio, 206 pruebas de frontend en verde, lint
  limpio, build de producción exitoso, y la suite de backend en verde.
- **Lo pendiente:** hay **8 escenarios de Playwright en rojo** (4 pruebas × 2
  perfiles de dispositivo). No son regresiones: son pruebas escritas contra una
  versión anterior de la interfaz que quedaron desactualizadas cuando se rediseñaron
  esas pantallas. Concretamente esperan un encabezado que se movió a otra pantalla,
  una ruta de navegación que cambió, un campo "Nombre" que ahora es ambiguo porque
  hay dos, y unos botones del studio que se renombraron. Está verificado contra una
  copia limpia del repositorio: fallan igual sin los cambios recientes.
- **Siguiente paso natural:** actualizar esas cuatro pruebas a la interfaz actual.

---

## 14. Preguntas frecuentes con respuestas cortas

**¿Por qué FastAPI y no Django?**
Porque la API es asíncrona por naturaleza —espera a modelos de lenguaje, a
proveedores de imágenes, a almacenamiento— y FastAPI con SQLAlchemy async maneja
esa espera sin bloquear. Django habría traído un ORM síncrono y un panel de
administración que no necesitábamos.

**¿Por qué Next.js sin framework CSS?**
Porque el diseño venía de un Figma con un sistema de tokens propio. Un framework
CSS habría impuesto sus escalas y habríamos peleado contra él. Con tokens propios
el código refleja el diseño uno a uno.

**¿Dónde está la "inteligencia artificial" exactamente?**
En tres lugares: el prompt se arma con el perfil del negocio y las reglas de marca
(`app/services/`), la respuesta se fuerza a cumplir un contrato JSON, y las
recomendaciones de plantillas se puntúan por coincidencia de plataforma, objetivo
y categoría.

**¿Es seguro?**
Sesión por cookie con CSRF, límite de peticiones en rutas sensibles, límite de
tamaño de cuerpo, validación de hosts, tokens de terceros cifrados con AES-256-GCM,
contraseñas con hash, y validación de configuración que impide arrancar en
producción con ajustes de desarrollo.

**¿Cuánto cuesta operarlo?**
Puede correr en cero: providers demo, almacenamiento local, Redis en memoria. Con
proveedores reales, el nivel rápido de OpenRouter está fijado al modelo gratuito y
la generación de imágenes tiene presupuesto diario por workspace con reserva
transaccional.

**¿Y si el modelo alucina?**
No importa tanto, porque la salida se valida contra un contrato: si no cumple la
forma, no llega al usuario. Y el resultado siempre es editable.

**¿Qué falta para producción?**
Actualizar las 4 pruebas E2E desactualizadas, conectar los proveedores reales por
variables de entorno, y ejecutar el chequeo de preparación de beta
(`npm run beta:check`).

---

## 15. Glosario

| Término | Qué significa aquí |
|---|---|
| **Artefacto** | Una pieza de contenido generada (post, guion, recomendación) con su estructura de campos |
| **Contrato** | JSON Schema que define la forma exacta de un dato. Fuente de verdad del proyecto |
| **Contexto acotado** | Una división del dominio dueña de sus propias tablas (identity, templates, library...) |
| **Provider** | Adaptador hacia un servicio externo (modelo de IA, almacenamiento, email) |
| **Modo demo** | Configuración en la que todo funciona sin credenciales, con datos deterministas |
| **Idempotencia** | Garantía de que repetir una petición no repite su efecto ni su costo |
| **Fail open** | Ante una falla, permitir el paso en vez de bloquear (correcto solo donde no hay nada que proteger) |
| **Fallback** | El comportamiento alterno cuando la ruta principal no está disponible |
| **Preflight** | Verificación previa de que una operación cara puede ejecutarse (presupuesto, cuota, permisos) |
| **Scroll-snap** | Función nativa del navegador que hace que el desplazamiento se detenga alineado a cada tarjeta |
| **Token de diseño** | Variable CSS con un rol semántico, no un color suelto |
| **Migración** | Cambio versionado del esquema de base de datos (Alembic) |
| **Workspace** | El espacio de trabajo al que pertenecen negocios, proyectos y consumo de IA |
