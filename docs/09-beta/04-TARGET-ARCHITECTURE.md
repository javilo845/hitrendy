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
