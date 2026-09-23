# HiTrendy — Plan maestro consolidado



---

<!-- SOURCE: 00-MASTER-PLAN.md -->

# Plan maestro de beta

## 1. Norte del producto

HiTrendy será un asistente de marketing para pequeños negocios. La beta no se medirá por la cantidad de pantallas ni de APIs, sino por completar correctamente este recorrido:

```text
crear cuenta
→ describir el negocio
→ confirmar la marca
→ recibir recomendaciones útiles
→ generar un post para Instagram
→ guardar el resultado
```

La promesa principal no es “acceso a muchas IAs”. La promesa es transformar el contexto de un negocio en contenido útil con la menor fricción posible.

## 2. Lo que ya está resuelto

Las cinco waves anteriores fortalecieron la base:

- Providers reales y configuración de runtime.
- Migraciones y seeds PostgreSQL.
- Reintentos idempotentes.
- E2E reales con PostgreSQL.
- CI para backend, frontend, migraciones y E2E.

Por eso la siguiente etapa no debe rehacer infraestructura. Debe conectar el producto real.

## 3. Bloques del plan

### Bloque A — Identidad real

- Registro temporal seguro.
- Onboarding obligatorio.
- Finalización atómica de cuenta, workspace interno, negocio, marca y sesión.
- Inicio con Google.
- Eliminación del modo demo de la experiencia pública.
- Guardas de rutas para onboarding incompleto.

### Bloque B — Persistencia y nube

- PostgreSQL administrado.
- Storage S3 compatible.
- Redis administrado.
- Backend y frontend desplegados.
- Cookies, CORS y CSRF correctos.
- Migraciones controladas.

### Bloque C — IA textual real

- OpenRouter.
- Router por capacidad.
- Modos rápido/equilibrado/calidad.
- Recomendaciones.
- Captions y posts.
- Registro de uso y costo.
- Degradación explícita cuando no hay cuota o dinero.

### Bloque D — Cuenta y configuración

- Datos personales.
- Negocio.
- Marca.
- Idiomas.
- Uso.
- Privacidad.
- Eliminación de cuenta.
- Administración auditada.

### Bloque E — Tendencias verificables

- Adaptadores por fuente.
- Datos con fecha, URL y región.
- Normalización y scoring.
- Recomendaciones personalizadas.
- Ejecución diaria y manual.
- Nunca convertir conocimiento general del LLM en “tendencia detectada”.

### Bloque F — Multimedia

- Imágenes después de cerrar texto.
- Conexiones sociales después de cerrar tendencias.
- Video como función avanzada y pagada.

## 4. Orden de implementación

```text
006A  Pending signup y finalización atómica
006B  Onboarding frontend y eliminación del demo público
006C  Google Sign-In
007A  Supabase PostgreSQL, Storage y Redis
007B  Despliegue beta, cookies, CORS y CSRF
008A  Registro de capacidades y estado de proveedores
008B  OpenRouter de texto y niveles de calidad
008C  Flujo “post de Instagram en cinco minutos”
009   Configuración, idiomas, uso y ciclo de cuenta
010A  Contrato de fuentes de tendencias
010B  YouTube + búsqueda/Trends + RSS
010C  Jobs diarios y pantalla Inicio
011   Generación de imágenes
012   Conexiones con redes propias
013   Generación de video
014   Preparación de beta cerrada
```

Cada subwave debe terminar con pruebas, documentación y reporte. No se deben combinar varias subwaves en un commit gigante.

## 5. Perfiles de costo

### Perfil `beta-zero-cost`

Adecuado para demostraciones y pocos usuarios:

- Supabase Free.
- Render Free para backend, aceptando cold starts.
- Upstash Redis Free.
- OpenRouter free router para texto.
- Resend Free.
- YouTube Data API con cuota predeterminada.
- SerpApi Free para una muestra pequeña.
- RSS permitido.

Limitaciones:

- El modelo gratuito puede cambiar o estar saturado.
- No se habilitan imágenes ni video reales.
- GNews gratis no se usa en una beta comercial.
- X se desactiva.
- TikTok/Instagram no se presentan como fuentes completas de tendencias.
- El backend puede tardar alrededor de un minuto en despertar si se usa Render Free.

### Perfil `beta-controlled-paid`

Adecuado para beta externa más confiable:

- Supabase Pro o la misma base Free con vigilancia y backups propios.
- Hosting sin cold starts.
- OpenRouter con saldo y límites.
- Proveedor comercial de noticias/búsqueda.
- Presupuesto máximo mensual.
- Imágenes habilitadas solo con créditos.
- Video desactivado inicialmente.

## 6. Reglas de degradación

La beta debe seguir siendo honesta cuando falta una integración:

| Capacidad ausente | Comportamiento |
|---|---|
| Modelo de texto pagado | Usar modelo gratuito permitido o bloquear con mensaje claro |
| Generación de imagen | Entregar briefing visual, formato y prompt; no fingir imagen |
| Video | Entregar guion y storyboard |
| Fuentes de tendencias | Mostrar “recomendaciones para tu negocio”, no “tendencias” |
| X sin créditos | Omitir X y señalar fuente no disponible |
| TikTok sin aprobación | Aceptar enlaces/manual input; no simular acceso |
| Noticias comerciales sin plan | Deshabilitar en producción |
| Cuota agotada | Mostrar siguiente reinicio y opciones disponibles |

## 7. Definición de terminado de la beta textual

- Registro y login funcionan desde una URL pública.
- El onboarding no usa solo `localStorage`.
- Existe exactamente un negocio activo por cuenta.
- Producción no permite provider demo.
- OpenRouter responde realmente.
- Se guarda el modelo, modalidad, tokens y costo reportado.
- La IA recibe contexto de negocio.
- La respuesta puede guardarse y recuperarse.
- La aplicación conoce qué capacidades están configuradas.
- No se filtran secretos al cliente.
- Tests unitarios, E2E y CI pasan.
- Se ha probado una cuenta nueva desde navegador incógnito.


---

<!-- SOURCE: 01-CURRENT-STATE-AUDIT.md -->

# Auditoría del estado actual

## Alcance

Auditoría estática del repositorio público `Starryboyjosh/Trend-AI`, rama `main`, realizada el 26 de julio de 2026. Las rutas indicadas deben volver a verificarse justo antes de implementar, porque el repositorio puede avanzar.

## 1. Resumen ejecutivo

El repositorio ya no es una maqueta vacía. Tiene backend FastAPI, frontend Next.js, PostgreSQL, Alembic, autenticación, negocios, perfiles de marca, conversaciones, artefactos, idempotencia, E2E y CI.

Sin embargo, el producto visible todavía mezcla dos identidades:

1. Una demo offline/determinista.
2. Una base de aplicación real.

La arquitectura de beta debe conservar los dobles de prueba, pero retirar el modo demo del recorrido de usuarios.

## 2. Identidad

Archivo principal verificado:

```text
starter/backend/app/identity/routes.py
```

Estado:

- `POST /auth/register`.
- `POST /auth/login`.
- `POST /auth/logout`.
- `GET /auth/me`.
- Hash de contraseña mediante `scrypt`.
- Sesiones persistidas y cookie HttpOnly.
- El registro actual crea inmediatamente:
  - usuario;
  - workspace;
  - membresía;
  - sesión.
- El request actual exige `workspace_name`.
- No hay flujo temporal de registro.
- No hay Google OAuth.
- No hay recuperación de contraseña.
- No hay endpoint completo de eliminación de cuenta.
- Cookie `SameSite=Strict`, lo cual debe revisarse para frontend y backend en dominios distintos.

## 3. Onboarding

Archivo verificado:

```text
starter/web/app/onboarding/page.tsx
```

Estado:

- Cinco pasos:
  - negocio;
  - audiencia;
  - canales;
  - marca;
  - revisión.
- El borrador se guarda en `localStorage`.
- La página está detrás de `ProtectedRoute`, así que ya existe una cuenta antes de entrar.
- Al final crea `Business` y luego `BrandProfile` mediante dos llamadas.
- Si falla la segunda llamada, puede quedar un negocio sin perfil completo.
- El flujo no corresponde a la decisión nueva de “cuenta finalizada al terminar onboarding”.

## 4. Configuración

Archivo verificado:

```text
starter/web/app/settings/page.tsx
```

Estado:

- Edita parcialmente el primer negocio encontrado.
- Edita perfil de marca.
- No incluye:
  - cuenta;
  - correo;
  - cambio de contraseña;
  - Google vinculado;
  - idioma de interfaz;
  - idioma de contenido;
  - consumo;
  - privacidad;
  - eliminación de cuenta;
  - sesiones.

La página ya es el lugar natural para absorber “Mi negocio”.

## 5. Modo demo

Archivos verificados:

```text
starter/web/lib/demo-mode.ts
starter/web/lib/api.ts
.env.example
README.md
demo/
docs/07-demo/
```

Estado:

- El modo demo del frontend se activa en localhost mediante `localStorage`.
- El cliente API puede desviar las operaciones a almacenamiento local.
- `.env.example` usa `AI_PROVIDER=demo`.
- El README presenta la demo offline como ruta rápida.
- Producción rechaza el provider demo de contenido, lo cual es correcto.
- El provider demo debe mantenerse solo para tests y desarrollo explícito, no como experiencia pública.

## 6. Providers

Archivos verificados:

```text
starter/backend/app/core/config.py
starter/backend/app/providers/factory.py
starter/backend/app/providers/content.py
starter/backend/app/providers/vision.py
```

Estado:

- Un provider de contenido global.
- Un modelo de contenido global.
- Un provider de visión global.
- Soporte `openai-compatible`.
- Reintentos y errores ya trabajados.
- Producción exige provider real de contenido.
- No existe router por capacidad/tier.
- No existe registro unificado de disponibilidad, cuota, pago o degradación.
- Visión demo todavía está permitida en producción por una decisión antigua de Phase 1.

## 7. Persistencia e infraestructura

Estado conocido y validado por waves anteriores:

- PostgreSQL.
- Alembic hasta revisión `013`.
- Seed de templates.
- E2E con PostgreSQL aislado.
- CI en GitHub Actions en verde.
- Docker Compose local.
- Configuración de Storage local/S3.
- Configuración Redis obligatoria en producción.

Pendiente:

- Base remota.
- Storage remoto.
- Redis remoto.
- Migraciones de staging.
- despliegue;
- cookies/CORS/CSRF en dominios reales.

## 8. Documentación desalineada

Documentos que todavía reflejan el enfoque demo o un MVP anterior:

```text
README.md
AGENTS.md
IMPLEMENTATION_PROMPT.md
project-manifest.yaml
docs/INDEX.md
docs/00-product/vision-and-scope.md
docs/00-product/user-flows.md
docs/00-product/roadmap.md
docs/06-implementation/agentic-playbook.md
docs/06-implementation/backlog.md
docs/07-demo/
demo/
```

No se recomienda eliminarlos inmediatamente. Primero deben dejar de ser fuente de verdad, mover lo histórico a un archivo y actualizar referencias.

## 9. Riesgos actuales

- Un modelo básico podría leer `AGENTS.md` y obedecer restricciones viejas contra tendencias.
- Otro modelo podría seguir el README y trabajar sobre `demo/` en vez de `starter/`.
- El registro y onboarding no son atómicos.
- El concepto técnico “workspace” se filtra al producto.
- No hay conciencia de disponibilidad económica de integraciones.
- El home podría llamar “tendencia” a una recomendación sin fuente.
- Producción requerirá Redis, pero aún no está seleccionado.
- El modo demo local puede ocultar fallos del backend real.
- Falta medir costo real por generación.

## 10. Regla de fuente de verdad propuesta

Mientras se migra la documentación:

1. Contratos y migraciones aceptadas.
2. Código y tests actuales.
3. Este paquete de arquitectura beta.
4. ADR aceptados.
5. Documentación actualizada de beta.
6. Documentación histórica.
7. Demo legacy.


---

<!-- SOURCE: 02-BETA-PRODUCT-CONTRACT.md -->

# Contrato del producto beta

## 1. Usuario objetivo

Dueño o encargado de un pequeño negocio latinoamericano que no necesita conocer marketing ni modelos de IA.

## 2. Promesa central

> Una persona crea su cuenta en HiTrendy y cinco minutos después puede hacer un post de Instagram ideal para su negocio.

## 3. Decisiones confirmadas

- Un negocio por cuenta durante la beta.
- Onboarding obligatorio.
- La cuenta se finaliza después de completar y confirmar todo el onboarding.
- Inicio con correo/contraseña y Google.
- Interfaz en español, inglés y portugués.
- Idioma del contenido configurable por negocio.
- Eliminación inmediata desde la perspectiva del usuario.
- Niveles de IA visibles: rápido, equilibrado, calidad.
- Prioridad:
  1. recomendaciones;
  2. textos y captions;
  3. imágenes;
  4. videos.
- Plataformas prioritarias: Instagram, TikTok y X.
- Región inicial de tendencias: Latinoamérica.
- Inicio de la aplicación: tendencias y oportunidades del negocio.
- Análisis de tendencias diario y actualización manual.
- Limpieza moderada del repositorio.

## 4. Flujo de alta

### Paso 1 — Acceso

- Nombre.
- Correo.
- Contraseña.
- Idioma de interfaz.
- Alternativa: continuar con Google.

### Paso 2 — Negocio

- Nombre comercial.
- Categoría.
- País.
- Ciudad.
- Descripción.
- Producto o servicio principal.
- Público objetivo.
- Sitio web opcional.

### Paso 3 — Canales y objetivo

- Instagram.
- TikTok.
- X.
- Objetivo:
  - ventas;
  - alcance;
  - interacción;
  - lanzamiento;
  - tráfico;
  - comunidad.

### Paso 4 — Marca

- Personalidad.
- Tono.
- Propuesta de valor.
- Colores.
- Logo opcional.
- Palabras preferidas.
- Palabras prohibidas.
- Idioma predeterminado del contenido.

### Paso 5 — Confirmación

Mostrar una síntesis en lenguaje natural:

```text
Esto es lo que entendí de tu negocio…
```

Solo después de confirmar se crean los registros activos y la sesión normal.

## 5. Flujo principal

```text
Inicio
→ oportunidad/recomendación
→ Crear post
→ elegir plataforma y objetivo
→ nivel rápido/equilibrado/calidad
→ generar
→ editar
→ guardar
```

El flujo también debe aceptar una solicitud libre desde chat.

## 6. Navegación

```text
Inicio
Crear
Conversaciones
Plantillas
Proyectos
Biblioteca
Configuración
```

No mostrar `Workspace` ni una sección principal separada llamada `Mi negocio`.

## 7. Configuración

### Cuenta
- nombre;
- correo;
- contraseña;
- Google;
- sesiones;
- cerrar sesión.

### Negocio
- todos los datos del onboarding.

### Marca
- tonos;
- colores;
- logo;
- propuesta;
- vocabulario.

### Idiomas
- interfaz;
- contenido.

### Uso
- consumo diario;
- recomendaciones;
- texto;
- imágenes;
- video;
- siguiente reinicio.

### Privacidad
- proveedores usados;
- descarga de datos;
- retención;
- eliminación.

### Zona de peligro
- eliminar cuenta;
- confirmación fuerte;
- revocar sesiones inmediatamente.

## 8. Vocabulario de producto

Usar:

- negocio;
- marca;
- cuenta;
- recomendación;
- tendencia detectada;
- fuente;
- nivel de calidad;
- uso.

No usar frente al usuario:

- workspace;
- provider;
- endpoint;
- tokens;
- idempotency key;
- model slug;
- migration;
- free router.

## 9. Regla de honestidad

- “Tendencia” requiere fuente externa, fecha y región.
- “Recomendación” puede basarse solo en el perfil del negocio.
- “Imagen generada” requiere archivo real.
- “Video generado” requiere trabajo finalizado.
- Una integración no configurada se muestra como no disponible.
- No se sustituyen datos faltantes por contenido inventado del LLM.


---

<!-- SOURCE: 03-FREE-PAID-API-MATRIX.md -->

# Matriz de APIs, costos y restricciones

**Corte de revisión:** 26 de julio de 2026.  
Los planes cambian. El backend deberá guardar la configuración real y el equipo debe revisar precios antes de cada despliegue.

## 1. Respuesta directa

Se puede iniciar una beta cerrada con aproximadamente **ocho piezas sin pago inicial**, pero no todas tienen calidad o términos adecuados para una beta comercial permanente:

1. Supabase Free — PostgreSQL y Storage.
2. Upstash Redis Free.
3. Render Free — backend con cold start y restricciones.
4. OpenRouter free models — texto de bajo volumen.
5. Resend Free — correo transaccional.
6. YouTube Data API — cuota diaria predeterminada.
7. SerpApi Free — 250 búsquedas al mes.
8. Google Sign-In — integración de identidad sin una tarifa por login publicada.

También se pueden usar feeds RSS públicos, pero no constituyen una única API y se deben respetar términos y derechos de cada fuente.

## 2. Clasificación

### Verde — útil para una beta pequeña

| Servicio | Costo inicial | Cuota/condición | Uso propuesto | Riesgo |
|---|---:|---|---|---|
| Supabase Free | $0 | 2 proyectos, 500 MB DB/proyecto, 1 GB Storage, 5 GB egress, 50k MAU | PostgreSQL y archivos | pausa/inactividad, sin backups automáticos |
| Upstash Redis Free | $0 | 256 MB, 10 GB bandwidth, 500k comandos/mes | rate limits, cache, jobs ligeros | no es SLA de producción |
| Resend Free | $0 | 3,000 emails/mes, 100/día, 1 dominio | verificación, reset password | límite diario |
| YouTube Data API | $0 con cuota | 10,000 unidades/día y cuotas por operación | señal de tendencias y videos | cuota y políticas |
| SerpApi Free | $0 | 250 búsquedas/mes | prototipo de Google Search/Trends | volumen muy bajo |
| OpenRouter free router | $0 | modelos gratuitos y rate limits bajos | recomendaciones/texto de demostración | latencia, disponibilidad y modelo variable |

### Amarillo — gratuito con condiciones fuertes

| Servicio | Condición | Decisión |
|---|---|---|
| Render Free | duerme tras 15 minutos, cold start cercano a un minuto, 750 horas; no recomendado para producción | válido para demo/beta cerrada |
| Instagram API | sin tarifa por llamada documentada, pero requiere cuenta profesional, permisos y revisión | integrar después, no contar como fuente de tendencias general |
| Google OAuth | requiere proyecto, credenciales, consentimiento y posible verificación de scopes | usar solo `openid email profile` al inicio |
| Google Trends API | alfa limitada a pocos testers | no usar como dependencia crítica |
| TikTok Content APIs | revisión de app y permisos | no confundir con acceso a tendencias |
| RSS/local sites | puede ser gratis | usar solo fuentes permitidas y atribuidas |

### Naranja — gratis solo para desarrollo/no comercial

| Servicio | Restricción | Decisión |
|---|---|---|
| Vercel Hobby | uso personal no comercial | no elegir para una beta comercial |
| GNews Free | desarrollo/testing, 100 requests/día, 12 h de atraso | deshabilitar en producción comercial |
| Reddit Data API | uso comercial requiere aprobación | no habilitar comercialmente sin permiso |

### Rojo — pago o crédito requerido

| Servicio | Modelo de cobro | Decisión |
|---|---|---|
| X API | consumo/créditos | desactivado por defecto |
| OpenRouter modelos premium | tokens/requests | opt-in con presupuesto |
| OpenRouter imágenes | por generación/uso | WAVE-011 |
| OpenRouter video | por trabajo generado | WAVE-013 |
| Railway después de prueba | crédito/prueba y luego cobro | no tratar como gratuito permanente |
| Proveedores comerciales de noticias | suscripción | evaluar en WAVE-010 |

## 3. Límites de OpenRouter

- Los modelos gratuitos tienen IDs con `:free` o pueden seleccionarse mediante `openrouter/free`.
- La disponibilidad de modelos gratuitos puede cambiar.
- Sin compras suficientes, la cuota diaria gratuita es baja.
- Con al menos $10 de créditos comprados históricamente, OpenRouter documenta una cuota diaria mayor para modelos gratuitos.
- Los modelos gratuitos son adecuados para pruebas y bajo volumen, no para prometer disponibilidad de producción.
- El endpoint de modelos expone capacidades y precios; precio `0` indica gratuito.
- Imágenes y video no deben asumirse gratis.

## 4. Cómo debe saberlo HiTrendy

No basta con variables de entorno. Se necesita un registro de capacidades.

Estados:

```text
available
unconfigured
disabled
restricted
quota_exhausted
payment_required
degraded
error
```

Ejemplo seguro enviado al frontend:

```json
{
  "advisor": {
    "status": "available",
    "tier": "free",
    "quality_levels": ["fast"],
    "message": null,
    "next_reset_at": "2026-07-27T00:00:00Z"
  },
  "image_generation": {
    "status": "payment_required",
    "tier": "paid",
    "quality_levels": [],
    "message": "La generación de imágenes no está habilitada en esta beta."
  },
  "x_trends": {
    "status": "disabled",
    "tier": "paid",
    "message": "X no está conectado."
  }
}
```

La respuesta nunca incluye:

- claves;
- saldo exacto del dueño;
- IDs secretos;
- errores internos;
- credenciales;
- URLs privadas.

## 5. Reglas por capacidad

### Texto gratuito agotado

- No cambiar silenciosamente a un modelo pagado.
- Retornar `AI_QUOTA_EXHAUSTED`.
- Mostrar el siguiente reinicio si se conoce.
- Permitir que un administrador active saldo pagado.

### Imagen no pagada

- Entregar:
  - concepto visual;
  - composición;
  - formato;
  - paleta;
  - prompt;
  - texto del post.
- No crear un placeholder y llamarlo “imagen generada”.

### Video no pagado

- Entregar guion, tomas y storyboard.
- Mantener la acción “Generar video” deshabilitada.

### Tendencias incompletas

- Mostrar fuentes disponibles.
- Etiquetar como recomendaciones si no hay evidencia externa.
- Nunca inventar datos de TikTok, Instagram o X.

## 6. Presupuesto recomendado de beta

Mientras el presupuesto sea desconocido:

```text
USAGE_ENFORCEMENT_MODE=soft
ALLOW_PAID_MODEL_FALLBACK=false
IMAGE_GENERATION_ENABLED=false
VIDEO_GENERATION_ENABLED=false
X_TRENDS_ENABLED=false
```

Configurar un tope mensual antes de activar cualquier fallback pagado.


---

<!-- SOURCE: 04-TARGET-ARCHITECTURE.md -->

# Arquitectura técnica objetivo

## 1. Vista general

```text
Navegador
  │
  ▼
Next.js
  │ HTTPS + credentials
  ▼
FastAPI
  ├── Identity / onboarding
  ├── Business / brand
  ├── Conversations / artifacts
  ├── Capabilities / usage
  ├── Trends
  └── Admin CLI/API
       │
       ├── PostgreSQL (Supabase)
       ├── Object Storage S3-compatible (Supabase Storage)
       ├── Redis (Upstash)
       ├── OpenRouter
       ├── Resend
       └── Source adapters
```

## 2. Fronteras

### Frontend

Responsable de:

- UX;
- traducciones;
- formularios;
- estados de carga;
- llamadas autenticadas;
- mostrar capacidades;
- no exponer secretos.

No responsable de:

- elegir credenciales;
- guardar balances;
- llamar OpenRouter directamente;
- conectarse a PostgreSQL;
- decidir si una fuente es comercialmente permitida.

### Backend

Responsable de:

- autenticación;
- autorización;
- negocio y marca;
- router de capacidades;
- selección de modelo;
- validación de cuota;
- persistencia;
- auditoría;
- normalización de errores;
- jobs;
- políticas de eliminación.

### PostgreSQL

Fuente de verdad para:

- usuarios;
- negocio;
- marca;
- configuración;
- conversaciones;
- artefactos;
- operaciones;
- tendencias;
- uso;
- auditoría.

### Redis

Usos permitidos:

- rate limiting;
- locks cortos;
- cache de catálogo de modelos;
- cache de capacidades;
- cola liviana o coordinación.

No debe ser la única copia de:

- sesiones importantes;
- uso facturable;
- tendencias;
- resultados de generación;
- jobs de purga.

## 3. Entornos

### local

- PostgreSQL Docker.
- MinIO/local storage.
- Redis Docker.
- Provider demo solo mediante una bandera explícita de desarrollo.
- E2E existentes.

### staging

- Datos separados.
- Servicios gratuitos permitidos.
- OpenRouter free.
- Sin usuarios reales sensibles.
- Migraciones automáticas controladas.
- Smoke tests.

### beta

- Base y Storage remotos.
- Credenciales reales.
- Provider demo prohibido.
- Cuotas soft.
- Logs y alertas.
- Backups definidos.
- Integraciones deshabilitadas cuando no tienen plan compatible.

## 4. Cookies y dominios

Opción preferida:

```text
app.hitrendy.example
api.hitrendy.example
```

Mismo dominio raíz facilita cookies.

Si se usan dominios ajenos distintos:

- `Secure=true`;
- `SameSite=None`;
- CORS con origen exacto;
- `credentials: include`;
- protección CSRF;
- no usar `*` con credenciales;
- probar Safari, Chrome y Firefox.

## 5. Patrón de adapters

Cada servicio externo implementa una interfaz interna estable.

```python
class CapabilityAdapter(Protocol):
    key: str
    async def health(self) -> CapabilityHealth: ...
    async def execute(self, request: CapabilityRequest) -> CapabilityResult: ...
```

Categorías:

- AI text;
- AI vision;
- AI image;
- AI video;
- trend source;
- email;
- storage;
- OAuth.

Las rutas no deben contener lógica específica de múltiples proveedores.

## 6. Fallos

Todo error externo se convierte en un error interno estable:

```text
PROVIDER_UNCONFIGURED
PROVIDER_RESTRICTED
PROVIDER_PAYMENT_REQUIRED
PROVIDER_QUOTA_EXHAUSTED
PROVIDER_RATE_LIMITED
PROVIDER_TEMPORARILY_UNAVAILABLE
PROVIDER_INVALID_RESPONSE
```

El usuario recibe un mensaje humano y `retryable`. Los logs reciben detalles técnicos sanitizados.

## 7. Jobs

Jobs síncronos:

- recomendaciones de texto rápidas;
- captions;
- posts.

Jobs asíncronos:

- tendencias programadas;
- imágenes que excedan timeout;
- video;
- purga de cuenta;
- exportación de datos;
- mantenimiento.

Todo job asíncrono requiere:

- ID;
- owner/workspace;
- estado;
- provider;
- timestamps;
- intentos;
- error normalizado;
- resultado;
- idempotency key.

## 8. Observabilidad mínima

- request ID;
- user/workspace ID hash o ID interno;
- capability;
- provider;
- model;
- latency;
- status;
- retry count;
- usage;
- cost;
- cache hit;
- error code.

No registrar:

- contraseña;
- cookie;
- API key;
- prompt completo con información sensible por defecto;
- contenido privado sin política.


---

<!-- SOURCE: 05-DATA-MODEL-AND-MIGRATIONS.md -->

# Modelo de datos y migraciones propuestas

## 1. Principios

- Mantener UUID/IDs y convenciones actuales.
- Una migración por cambio coherente.
- PostgreSQL es la referencia.
- Conservar compatibilidad con SQLite solo donde la suite rápida la requiera.
- No modificar migraciones históricas salvo incompatibilidad comprobada.
- La siguiente revisión debe partir del head real en el momento de implementación.

## 2. Registro temporal

### `pending_signups`

Campos mínimos:

```text
id
email_normalized
name
password_hash nullable
oauth_provider nullable
oauth_subject nullable
interface_locale
draft_json
current_step
token_hash
expires_at
created_at
updated_at
```

Reglas:

- Nunca guardar contraseña en texto.
- Token aleatorio solo en cookie; DB guarda hash.
- Email reservado mientras el draft esté vigente.
- Expiración, por ejemplo, 24 horas.
- Índices por email y token hash.
- Google y contraseña no requieren exactamente los mismos campos.

## 3. Usuarios e identidad

Cambios propuestos:

### `users`

```text
interface_locale
status
deleted_at nullable
```

Estados:

```text
active
deleting
disabled
```

### `oauth_accounts`

```text
id
user_id
provider
provider_subject
email_at_link_time
created_at
last_login_at
```

Restricción única:

```text
(provider, provider_subject)
```

## 4. Un negocio por cuenta beta

Conservar `Workspace` internamente.

Aplicar:

```text
un usuario owner
→ un workspace primario
→ un business activo
```

Opciones:

- restricción única `businesses.workspace_id`;
- o campo `is_primary` con índice parcial único.

Preferencia beta: una restricción simple por workspace, siempre que los tests actuales no dependan de múltiples negocios.

## 5. Preferencias

### `user_preferences`

```text
user_id
interface_locale
timezone
created_at
updated_at
```

### Negocio

Agregar o normalizar:

```text
content_locale
website_url
onboarding_completed_at
```

Usar códigos BCP 47:

```text
es
en
pt-BR
es-HN
```

La interfaz inicial solo expone `es`, `en`, `pt`.

## 6. Registro de capacidades

### `integration_configs`

No almacenar la clave directamente si el secreto vive en el proveedor de hosting.

```text
key
enabled
tier
environment
configuration_metadata_json
updated_at
```

### `integration_health`

```text
integration_key
status
last_checked_at
last_success_at
last_error_code
quota_limit nullable
quota_used nullable
quota_reset_at nullable
```

## 7. Model routing

### `model_routes`

```text
capability
quality_tier
provider
model_id
enabled
requires_paid
fallback_priority
input_modalities
output_modalities
max_cost_per_operation nullable
updated_at
```

Restricción única:

```text
(capability, quality_tier, provider, model_id)
```

No guardar el catálogo completo de OpenRouter como fuente de verdad permanente. Cachearlo y fijar rutas aprobadas.

## 8. Uso

### `usage_events`

Ledger inmutable:

```text
id
user_id
workspace_id
capability
provider
model_id
units
prompt_tokens nullable
completion_tokens nullable
provider_cost_usd nullable
request_id
generation_job_id nullable
created_at
```

### `usage_allowances`

```text
workspace_id
period_type
period_start
period_end
recommendation_limit nullable
text_limit nullable
image_limit nullable
video_limit nullable
enforcement_mode
```

### `usage_adjustments`

```text
id
workspace_id
actor_user_id
capability nullable
delta
reason
created_at
```

No editar directamente el ledger.

## 9. Tendencias

### `trend_runs`

```text
id
region
started_at
completed_at
status
trigger
source_set_hash
```

### `trend_items`

```text
id
canonical_topic
region
language
first_seen_at
last_seen_at
freshness_score
growth_score
cross_source_score
confidence
```

### `trend_evidence`

```text
id
trend_item_id
source
source_url
external_id nullable
published_at nullable
observed_at
metrics_json
title
snippet
```

### `business_trend_scores`

```text
business_id
trend_item_id
relevance_score
platform_fit_score
final_score
explanation_json
computed_at
```

## 10. Generación multimedia

### `generation_jobs`

```text
id
workspace_id
user_id
capability
status
provider
model_id
quality_tier
request_hash
idempotency_key
provider_job_id nullable
result_asset_id nullable
cost_usd nullable
error_code nullable
created_at
updated_at
completed_at nullable
```

### `generated_assets`

Reutilizar el modelo de archivos/artefactos existente cuando sea posible. Evitar dos sistemas paralelos.

## 11. Eliminación de cuenta

### `account_deletion_jobs`

```text
id
user_id
requested_at
status
last_step
completed_at nullable
error_code nullable
```

Flujo:

1. Marcar cuenta `deleting`.
2. Revocar sesiones.
3. Bloquear login.
4. Borrar/anonimizar filas.
5. Borrar objetos Storage.
6. Conservar solo auditoría mínima sin PII, si la política lo permite.

## 12. Estrategia de migración

Cada subwave debe:

1. Crear migración.
2. Aplicar desde DB vacía.
3. Aplicar sobre DB en head anterior.
4. Repetir `upgrade head`.
5. Ejecutar pruebas PostgreSQL.
6. Probar constraints.
7. Documentar downgrade si es seguro.
8. No borrar datos reales silenciosamente.


---

<!-- SOURCE: 06-AUTH-ONBOARDING-SETTINGS.md -->

# Autenticación, onboarding y configuración

## 1. Problema actual

El registro actual crea una cuenta antes de conocer el negocio. El onboarding posterior usa `localStorage` y dos llamadas separadas. Eso contradice la decisión de finalizar la cuenta al confirmar todo el proceso.

## 2. Flujo recomendado

### Inicio de registro por correo

```http
POST /api/v1/auth/signup/start
```

Request:

```json
{
  "name": "Ana",
  "email": "ana@example.com",
  "password": "contraseña-larga",
  "interface_locale": "es"
}
```

Respuesta:

```json
{
  "signup": {
    "status": "pending",
    "current_step": "business",
    "expires_at": "..."
  }
}
```

El backend crea `pending_signup`, guarda hash de contraseña y coloca cookie HttpOnly temporal.

### Guardar borrador

```http
PATCH /api/v1/auth/signup/draft
```

- Autorizado por cookie de signup.
- Valida campos por sección.
- Persiste en servidor.
- Idempotente.
- No crea todavía usuario activo.

### Completar

```http
POST /api/v1/auth/signup/complete
Idempotency-Key: ...
```

Una sola transacción crea:

- User.
- Workspace.
- WorkspaceMember.
- Business.
- BrandProfile.
- UserPreferences.
- AuthSession.

Después elimina o marca consumido el pending signup.

## 3. Google

Flujo:

```text
GET /auth/google/start
→ state + PKCE
→ Google
→ callback backend
→ pending signup
→ onboarding
→ complete
```

Solicitar solo:

```text
openid
email
profile
```

No pedir permisos de YouTube, Drive ni redes durante el registro.

## 4. Seguridad

- CSRF en endpoints mutables autenticados por cookie.
- State y PKCE para OAuth.
- Rate limit por IP/email.
- Respuestas genéricas para evitar enumeración.
- Password mínimo y máximo.
- Token de signup rotado cuando cambia el nivel de autenticación.
- Expiración de pending signup.
- Auditoría de login y eliminación.
- No guardar password en frontend.
- No incluir password en logs.
- No usar JWT en localStorage.

## 5. Rutas frontend

Públicas:

```text
/login
/signup
/signup/business
/signup/channels
/signup/brand
/signup/review
```

Privadas:

```text
/dashboard
/create
/conversations
/projects
/library
/settings/*
```

Reglas:

- Usuario activo sin negocio: redirigir a recuperación/onboarding.
- Pending signup: solo puede navegar por signup.
- Usuario autenticado completo: no volver a signup.
- Demo mode no puede saltar autenticación.

## 6. Configuración

Subrutas sugeridas:

```text
/settings/account
/settings/business
/settings/brand
/settings/language
/settings/usage
/settings/privacy
```

Una navegación de tabs o sidebar, manteniendo responsive.

## 7. Idiomas

Frontend:

- Diccionarios `es`, `en`, `pt`.
- Sin texto importante hardcodeado.
- Locale inicial del signup.
- Persistencia en usuario.
- Fallback `es`.

Contenido:

- Guardado en negocio.
- Disponible para prompts.
- No depende del idioma de la UI.

## 8. Eliminación inmediata

Endpoint:

```http
DELETE /api/v1/account
```

Requerir:

- contraseña reciente para cuentas password;
- reautenticación Google para cuentas solo OAuth;
- texto de confirmación;
- CSRF.

Respuesta `202 Accepted`:

- la cuenta queda deshabilitada inmediatamente;
- sesiones revocadas;
- job de purga inicia;
- el usuario no vuelve a entrar.

## 9. Tests mínimos

- Signup start password.
- Signup draft.
- Expiración.
- Email duplicado.
- Complete atómico.
- Repetición idempotente.
- Fallo en Business revierte User.
- Google callback state inválido.
- Google signup completo.
- Guardas frontend.
- Recarga conserva borrador del servidor.
- Cuenta eliminada no puede hacer login.
- Aislamiento entre signups.


---

<!-- SOURCE: 07-AI-CAPABILITY-ROUTER.md -->

# Router de capacidades de IA

## 1. Objetivo

Separar “qué quiere hacer el usuario” de “qué proveedor/modelo está disponible”.

Capacidades iniciales:

```text
advisor
copywriter
vision_review
image_generation
video_generation
trend_analysis
```

Niveles:

```text
fast
balanced
quality
```

## 2. Regla principal

El usuario elige nivel, no modelo. El administrador define rutas aprobadas.

Ejemplo:

```text
advisor/fast       → OpenRouter free route
advisor/balanced   → modelo pagado A
advisor/quality    → modelo pagado B
copywriter/fast    → modelo estructurado económico
```

## 3. Registro de capacidades

Servicio interno:

```python
class CapabilityRegistry:
    async def get_public_snapshot(self, principal) -> PublicCapabilities: ...
    async def resolve(self, capability, quality_tier) -> ResolvedRoute: ...
    async def record_outcome(self, route, outcome) -> None: ...
```

Estados:

- `available`
- `unconfigured`
- `disabled`
- `restricted`
- `quota_exhausted`
- `payment_required`
- `degraded`
- `error`

## 4. Endpoint público seguro

```http
GET /api/v1/capabilities
```

Debe responder solo lo que la UI necesita:

- si está disponible;
- niveles permitidos;
- mensaje;
- reinicio de cuota;
- fallback funcional.

No exponer slug técnico por defecto. Puede enviarse un `route_label` interno solo a admins.

## 5. Contexto para el LLM

La IA debe saber qué puede ofrecer, pero no necesita conocer secretos ni saldo monetario.

Bloque interno:

```json
{
  "available_actions": {
    "text_post": true,
    "image_generation": false,
    "video_generation": false,
    "trend_sources": ["youtube", "search"]
  },
  "unavailable_actions": {
    "x_trends": "not_configured",
    "video_generation": "payment_required"
  }
}
```

Reglas del system prompt:

- No decir “ya generé una imagen” si la capacidad está deshabilitada.
- No citar tendencias de una fuente ausente.
- Ofrecer el fallback permitido.
- No revelar mensajes internos de facturación.
- No sugerir que el usuario compre saldo del dueño del sistema.

## 6. OpenRouter

Integración:

- Base URL OpenAI-compatible.
- API key solo backend.
- `HTTP-Referer` y título configurables.
- Catálogo `/models` cacheado.
- Fijar rutas aprobadas en DB/config.
- Verificar modalidad y parámetros.
- Detectar precio `0` para rutas gratuitas.
- Registrar modelo real usado si el free router lo reporta.
- No usar fallback pagado sin bandera explícita.

## 7. Selección de modelos

No hardcodear una lista eterna. En cada revisión:

1. Consultar catálogo.
2. Filtrar por modalidad.
3. Filtrar por structured outputs cuando aplique.
4. Filtrar por costo máximo.
5. Ejecutar evaluación con casos de HiTrendy.
6. Aprobar manualmente rutas.
7. Guardar versión de evaluación.

Casos de evaluación:

- recomendación de negocio;
- caption en español;
- caption en portugués;
- JSON válido;
- respeto de palabras prohibidas;
- CTA;
- no inventar tendencias;
- latencia;
- costo.

## 8. Contratos de salida

### Recomendación

```json
{
  "summary": "...",
  "reasoning_summary": "...",
  "ideas": [],
  "assumptions": [],
  "source_mode": "business_context"
}
```

### Post

```json
{
  "platform": "instagram",
  "headline": "...",
  "caption": "...",
  "cta": "...",
  "hashtags": [],
  "visual_brief": {
    "format": "4:5",
    "subject": "...",
    "composition": "...",
    "on_image_text": "..."
  }
}
```

Validar con Pydantic. Reparar JSON solo una vez; no aceptar texto libre silenciosamente.

## 9. Costos y eventos

Registrar:

- capability;
- tier;
- provider;
- model;
- tokens;
- costo informado;
- latency;
- status;
- fallback;
- request ID.

## 10. Fallbacks

```text
paid balanced unavailable
→ approved free route, solo si ALLOW_FREE_FALLBACK=true
→ o error transparente
```

Nunca:

```text
free quota exhausted
→ paid model sin autorización
```

## 11. Pruebas

- registry status.
- public snapshot sanitizado.
- model resolution.
- no paid fallback.
- free route.
- 402 payment required.
- 429 quota.
- degraded provider.
- unavailable image fallback.
- prompt capability context.
- structured output.
- usage ledger.


---

<!-- SOURCE: 08-TRENDS-ENGINE.md -->

# Motor de tendencias verificables

## 1. Definición

Una tendencia es un tema con evidencia externa reciente. Una recomendación es una idea derivada del negocio. No son sinónimos.

## 2. Fuentes por prioridad

Decisión del producto:

1. búsqueda de Google;
2. YouTube;
3. TikTok;
4. Instagram;
5. noticias;
6. Reddit;
7. sitios locales.

Disponibilidad técnica real para primera versión:

### Activables

- SerpApi Free para prototipo de Google Search/Trends.
- YouTube Data API.
- RSS y sitios locales permitidos.

### Condicionales

- Google Trends oficial: alfa limitada.
- Noticias comerciales: requieren plan válido.
- Instagram profesional: datos de cuenta autorizada, no firehose global.
- TikTok: Research API no disponible para uso comercial.
- Reddit comercial: requiere aprobación.
- X: pago por consumo.

## 3. Primera versión honesta

```text
YouTube
+ Search/Trends provider
+ RSS local
→ candidatos
→ deduplicación
→ scoring
→ personalización
```

No incluir TikTok/Instagram/X como fuente automática hasta tener acceso válido.

El usuario sí puede proporcionar enlaces manualmente para análisis.

## 4. Interfaz de fuentes

```python
class TrendSource(Protocol):
    key: str
    async def availability(self) -> SourceAvailability: ...
    async def collect(self, query: TrendQuery) -> list[TrendEvidence]: ...
```

`TrendEvidence`:

```json
{
  "source": "youtube",
  "external_id": "...",
  "url": "...",
  "title": "...",
  "published_at": "...",
  "observed_at": "...",
  "region": "HN",
  "language": "es",
  "metrics": {}
}
```

## 5. Pipeline

1. Construir términos desde categoría, producto, ubicación y plataformas.
2. Recolectar por región LATAM.
3. Normalizar idioma y timestamps.
4. Agrupar semánticamente sin perder evidencia.
5. Calcular crecimiento/frescura.
6. Cruzar fuentes.
7. Filtrar spam y temas inseguros.
8. Calcular relevancia del negocio.
9. Generar explicación con LLM.
10. Persistir evidencia y resultado.

## 6. Scoring inicial

```text
30% crecimiento
25% relevancia al negocio
15% frescura
15% coincidencia regional
10% presencia en varias fuentes
 5% ajuste a plataforma
```

Los pesos deben estar en configuración y versionados.

## 7. Frecuencia

- Job diario.
- Botón de actualización manual.
- Cooldown por negocio.
- Reusar resultados regionales.
- No hacer una recolección completa por cada usuario.

## 8. Home

Cada tarjeta:

- tema;
- fuente(s);
- fecha;
- región;
- confianza;
- razón de relevancia;
- ideas;
- botón “Crear post”;
- enlaces.

Cuando no hay fuentes:

```text
Recomendaciones para tu negocio
```

No:

```text
Tendencias de hoy
```

## 9. Cuotas

- Source adapter consulta capability registry.
- Presupuesto por ejecución.
- Cache.
- Límite por día.
- Si SerpApi llega a 250 búsquedas, marcar agotado.
- YouTube usa presupuesto de cuota.
- Fuentes deshabilitadas no bloquean el pipeline completo.

## 10. Seguridad y cumplimiento

- Respetar términos.
- Guardar extractos mínimos.
- No republicar artículos completos.
- Atribuir URL y fecha.
- Permitir borrar evidencia de usuario.
- No scraping oculto.
- No evadir bloqueos.
- No afirmar acceso oficial cuando es indirecto.

## 11. Pruebas

- adapters fake.
- deduplicación.
- scoring determinista.
- fuente agotada.
- ejecución parcial.
- no trend without evidence.
- enlaces y timestamps.
- aislamiento regional.
- job diario idempotente.
- manual cooldown.


---

<!-- SOURCE: 09-USAGE-COST-AND-ADMIN.md -->

# Uso, costos y administración

## 1. Objetivo

Mostrar desgaste durante la demostración sin imponer cobro todavía y sin crear una puerta trasera.

## 2. Modos

```text
off   → registrar, no mostrar ni bloquear
soft  → registrar, mostrar y advertir
hard  → registrar y bloquear
```

Beta inicial:

```text
USAGE_ENFORCEMENT_MODE=soft
```

## 3. Unidades

Separadas:

- recomendaciones;
- textos;
- imágenes;
- videos;
- refresh de tendencias.

No presentar tokens al usuario. Mostrar unidades comprensibles.

## 4. Ledger

Cada operación exitosa o facturable crea `usage_event`.

No recalcular solo desde logs. No editar eventos históricos.

## 5. UI

Configuración → Uso:

- barra del periodo;
- usado/restante;
- fecha de reinicio;
- desglose;
- advertencias;
- capacidades deshabilitadas.

En soft mode, llegar a cero no bloquea, pero la UI muestra el estado de demostración.

## 6. Herramienta administrativa

No usar comando secreto incrustado en el navegador.

CLI:

```bash
python -m app.admin.usage reset --email demo@example.com --reason "feria"
```

Requisitos:

- solo entorno autorizado;
- requiere credencial/admin;
- confirmación;
- escribe `usage_adjustment`;
- registra actor, fecha y motivo;
- nunca imprime API keys;
- tests.

Panel administrativo futuro:

```text
/admin/usage
```

No enlazado para usuarios normales y protegido por rol real, no por URL oculta.

## 7. Control de gasto

Variables:

```text
ALLOW_PAID_MODEL_FALLBACK=false
MONTHLY_AI_BUDGET_USD=0
MAX_TEXT_COST_USD=...
MAX_IMAGE_COST_USD=...
MAX_VIDEO_COST_USD=...
```

Antes de ejecutar:

1. Resolver capacidad.
2. Verificar allowance.
3. Verificar costo máximo conocido.
4. Reservar uso estimado.
5. Ejecutar.
6. Registrar costo real.
7. Reconciliar reserva.

## 8. Reglas

- Sin saldo: no ejecutar capacidad pagada.
- 402: `payment_required`.
- 429: `quota_exhausted` o `rate_limited`.
- No hacer fallback pagado.
- El usuario no ve el saldo del dueño.
- El administrador ve costo agregado.
- Nunca permitir costo ilimitado de video.

## 9. Pruebas

- soft mode.
- hard mode.
- reset auditado.
- usuario no admin rechazado.
- reserva concurrente.
- costo real.
- cuota agotada.
- periodo reiniciado.


---

<!-- SOURCE: 10-DEPLOYMENT-ENVIRONMENTS.md -->

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


---

<!-- SOURCE: 11-REPO-DOCUMENTATION-CLEANUP.md -->

# Plan de limpieza moderada del repositorio

## 1. Política

No borrar por impulso. Primero clasificar, luego retirar referencias, después archivar y finalmente eliminar duplicados confirmados.

## 2. Mantener como núcleo

```text
.github/
contracts/
design/
scripts/
starter/backend/
starter/web/
docker-compose.yml
.env.example
package.json
package-lock.json
Makefile
```

## 3. Actualizar

```text
README.md
AGENTS.md
CLAUDE.md
project-manifest.yaml
docs/INDEX.md
docs/00-product/
docs/02-ux/
docs/03-architecture/
docs/04-ai/
docs/05-api/
docs/06-implementation/
```

Cambios:

- beta como ruta principal;
- demo como legacy/test;
- tendencias dentro del roadmap;
- waves 001–005 marcadas como realizadas;
- waves 006+ como plan activo;
- nueva fuente de verdad.

## 4. Archivar

Destino:

```text
archive/legacy-demo/
```

Candidatos:

```text
demo/
docs/07-demo/
IMPLEMENTATION_PROMPT.md
backlogs reemplazados
prompts antiguos
```

Solo mover después de:

- revisar referencias;
- actualizar CI/scripts;
- confirmar que nadie los importa;
- conservar historial Git.

## 5. Conservar funcionalmente, pero ocultar

Provider demo:

- mantener para unit tests;
- mantener para desarrollo explícito;
- renombrar conceptualmente a `fake/test provider` en documentación;
- no ofrecer botón de demo;
- no permitir producción.

## 6. `AGENTS.md`

Debe indicar:

- `starter/` es implementación principal.
- No usar `demo/`.
- No inventar tendencias.
- Leer el plan beta.
- Ejecutar CI equivalente.
- No hacer commit/push.
- No modificar waves anteriores sin bug demostrado.
- No activar proveedores pagados.
- No exponer secretos.

## 7. `project-manifest.yaml`

Reescribir con YAML válido:

- versión;
- estado;
- entrypoints;
- runtimes;
- servicios;
- migración head;
- capacidades;
- documentos fuente;
- comandos;
- no-goals;
- completed waves;
- active wave.

Validar en CI.

## 8. Nuevo índice

Agregar:

```text
docs/09-beta/
```

Con los documentos principales de este paquete después de revisión.

## 9. No versionar

- handoff zips temporales;
- `.env`;
- `.venv`;
- `node_modules`;
- DB locales;
- uploads locales;
- resultados de agentes;
- logs;
- caches.

## 10. Entrega de limpieza futura

La limpieza debe ser una wave separada con:

- inventario;
- mapa de referencias;
- diff;
- tests;
- enlaces corregidos;
- ninguna eliminación silenciosa.


---

<!-- SOURCE: 12-AGENT-IMPLEMENTATION-STANDARD.md -->

# Estándar de implementación para modelos de código

Este documento está escrito para que modelos menos capaces produzcan cambios revisables.

## 1. Antes de editar

El agente debe:

1. Leer el prompt completo.
2. Ejecutar `git status --short`.
3. Identificar cambios no relacionados.
4. Inspeccionar archivos reales.
5. Localizar tests existentes.
6. Confirmar migración head.
7. Resumir plan en máximo diez pasos.
8. No editar hasta completar inspección.

## 2. Regla de alcance

- Una subwave por ejecución.
- No refactors estéticos fuera del objetivo.
- No cambiar contratos sin pruebas.
- No añadir nueva librería si la existente resuelve el problema.
- No modificar migraciones históricas.
- No usar `git add .`.
- No commit.
- No push.
- No tocar handoffs.

## 3. Código

- Tipos explícitos.
- Errores normalizados.
- Dependencias inyectables.
- Secretos solo por configuración.
- Operaciones externas con timeout.
- Idempotencia en acciones mutables importantes.
- Transacciones para operaciones atómicas.
- Sin rutas absolutas.
- Sin placeholders presentados como funciones.
- Sin fallbacks pagados implícitos.

## 4. Base de datos

- Nueva migración.
- Constraints e índices.
- PostgreSQL real.
- Upgrade desde vacío.
- Upgrade desde head anterior.
- Upgrade repetido.
- Tests de concurrencia cuando aplique.
- No borrar datos sin migración de datos.

## 5. API

Cada endpoint debe definir:

- auth;
- request;
- response;
- errores;
- idempotencia;
- rate limit;
- side effects;
- auditoría.

## 6. Frontend

- Estados loading/error/empty/success.
- Doble envío protegido.
- Accesibilidad.
- Responsive.
- Textos traducibles.
- No almacenar secretos.
- No usar `localStorage` como fuente de verdad de datos críticos.
- Mostrar capability status.

## 7. Proveedores

- Adapter.
- Fake.
- health.
- timeouts.
- error mapping.
- usage.
- cost.
- no external call in normal tests.

## 8. Pruebas obligatorias

Backend:

```bash
python -m ruff check .
python -m pytest -m "not e2e"
TEST_DATABASE_URL=... python -m pytest -m e2e
```

Frontend:

```bash
npm test
npm run typecheck
npm run lint
npm run build
```

Ejecutar scripts reales del repo si difieren.

## 9. Entrega

Formato:

### Resumen
### Análisis previo
### Archivos modificados
### Migraciones
### Contratos
### Seguridad
### Pruebas y resultados
### Hallazgos
### Limitaciones
### Checklist

No declarar completo con pruebas esenciales omitidas.

## 10. Prohibiciones

- Credenciales reales.
- scraping no autorizado;
- fake trends;
- puertas traseras;
- `continue-on-error` en CI esencial;
- `|| true`;
- desactivar tests;
- cambiar a Firebase;
- duplicar sistemas de autenticación;
- introducir Supabase Auth sin ADR;
- poner OpenRouter key en Next.js.


---

<!-- SOURCE: 13-DECISION-RECORDS.md -->

# Decisiones de arquitectura propuestas

## ADR-BETA-001 — PostgreSQL permanece como base principal

**Estado:** propuesto para aceptar.  
**Decisión:** usar PostgreSQL administrado; Supabase es candidato de hosting, no un cambio de modelo de datos.  
**Razón:** SQLAlchemy, Alembic, relaciones y E2E ya existen.  
**Consecuencia:** no usar Firebase como reemplazo.

## ADR-BETA-002 — Autenticación propia + Google

**Decisión:** conservar usuarios/sesiones del backend y añadir OAuth account linking.  
**Razón:** evitar migrar simultáneamente identidad y persistencia.  
**Consecuencia:** no adoptar Supabase Auth en la primera beta.

## ADR-BETA-003 — Cuenta finalizada al completar onboarding

**Decisión:** pending signup temporal, finalización atómica.  
**Razón:** decisión de producto confirmada.  
**Consecuencia:** nueva tabla y endpoints.

## ADR-BETA-004 — Un negocio visible por cuenta

**Decisión:** conservar workspace internamente; imponer un negocio activo.  
**Razón:** UX simple sin destruir extensibilidad.

## ADR-BETA-005 — Capability router

**Decisión:** seleccionar modelo por capacidad y nivel.  
**Razón:** múltiples modelos, cuotas y proveedores.  
**Consecuencia:** deprecar gradualmente el único `AI_MODEL`.

## ADR-BETA-006 — Free no significa disponible

**Decisión:** estado dinámico y degradación.  
**Razón:** cuotas, saturación, restricciones y términos.  
**Consecuencia:** endpoint de capacidades.

## ADR-BETA-007 — Tendencias requieren evidencia

**Decisión:** una tendencia debe guardar fuente, URL, fecha y región.  
**Razón:** evitar alucinaciones.

## ADR-BETA-008 — Uso como ledger

**Decisión:** eventos inmutables y ajustes auditados.  
**Razón:** costos y demo.

## ADR-BETA-009 — Sin comando secreto

**Decisión:** reset de uso por CLI/admin autenticado.  
**Razón:** una puerta trasera oculta es insegura.

## ADR-BETA-010 — Beta textual antes de multimedia

**Decisión:** cerrar cuenta, nube y texto antes de imagen/video.  
**Razón:** alcanza la promesa inicial con menor riesgo y costo.


---

<!-- SOURCE: 14-SOURCE-REGISTER.md -->

# Registro de fuentes

Revisadas el 26 de julio de 2026. Los precios y términos deben volver a verificarse al implementar.

## Repositorio

- Repositorio: https://github.com/Starryboyjosh/Trend-AI
- Variables: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/.env.example
- Config backend: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/starter/backend/app/core/config.py
- Factory providers: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/starter/backend/app/providers/factory.py
- Identity routes: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/starter/backend/app/identity/routes.py
- Onboarding: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/starter/web/app/onboarding/page.tsx
- Settings: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/starter/web/app/settings/page.tsx
- Demo mode: https://raw.githubusercontent.com/Starryboyjosh/Trend-AI/main/starter/web/lib/demo-mode.ts

## Servicios

- OpenRouter free router: https://openrouter.ai/docs/guides/routing/routers/free-router
- OpenRouter limits: https://openrouter.ai/docs/api_reference/limits
- OpenRouter models/pricing: https://openrouter.ai/docs/guides/overview/models
- Supabase billing: https://supabase.com/docs/guides/platform/billing-on-supabase
- Supabase S3 compatibility: https://supabase.com/docs/guides/storage/s3/compatibility
- Render Free: https://render.com/docs/free
- Vercel Hobby: https://vercel.com/docs/plans/hobby
- Vercel fair use: https://vercel.com/docs/limits/fair-use-guidelines
- Upstash Redis pricing: https://upstash.com/pricing/redis
- Resend pricing: https://resend.com/pricing
- YouTube Data API: https://developers.google.com/youtube/v3/getting-started
- SerpApi pricing: https://serpapi.com/pricing
- GNews pricing: https://gnews.io/pricing
- X developer platform: https://developer.x.com/
- Google OAuth: https://developers.google.com/identity/protocols/oauth2
- Google OIDC: https://developers.google.com/identity/openid-connect/openid-connect
- Instagram Platform: https://developers.facebook.com/documentation/instagram-platform
- TikTok Research API: https://developers.tiktok.com/products/research-api/
- TikTok Research FAQ: https://developers.tiktok.com/doc/research-api-faq
- Google Trends API alpha: https://developers.google.com/search/blog/2025/07/trends-api
- Reddit developer terms: https://redditinc.com/policies/developer-terms
- Reddit commercial API statement: https://redditinc.com/news/reddit-and-google-expand-partnership
