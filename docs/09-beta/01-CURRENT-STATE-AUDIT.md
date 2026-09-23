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
