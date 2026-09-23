# WAVE-006A — Registro temporal y finalización atómica

## Objetivo

Implementar el backend para comenzar, guardar y completar un registro obligatorio sin crear una cuenta activa antes de confirmar el onboarding.

## Contexto del repositorio


El registro actual de `identity/routes.py` crea User, Workspace y Session inmediatamente y exige `workspace_name`. El onboarding actual ocurre después. Esta wave cambia solo el backend y conserva login existente para usuarios ya creados.


## Alcance


- Tabla/modelo de pending signup.
- Endpoints start, get, patch draft, cancel y complete.
- Cookie temporal HttpOnly.
- Finalización transaccional.
- Compatibilidad temporal con `/auth/register` documentada y deprecada, sin romper tests existentes hasta WAVE-006B.
- Limpieza de drafts expirados.


## Inspección obligatoria

Antes de editar:


- `starter/backend/app/identity/`
- `starter/backend/app/business/`
- dependencias de DB y principal;
- migraciones `starter/backend/alembic/versions/`;
- tests identity/business/E2E;
- contratos existentes.


No asumas rutas adicionales. Localiza modelos, schemas, dependencias y tests relacionados.

## Secuencia de implementación


1. Diseñar schemas Pydantic por paso.
2. Añadir migración posterior al head real.
3. Guardar password únicamente como hash.
4. Crear token aleatorio y persistir solo su hash.
5. Implementar cookie `hitrendy_signup`.
6. Implementar PATCH idempotente por versión/updated_at.
7. En `complete`, validar todos los campos.
8. Crear User, Workspace, Membership, Business, BrandProfile, Preferences y Session dentro de una transacción.
9. Consumir el pending signup.
10. Añadir rate limits y errores estables.
11. Mantener usuarios antiguos funcionales.


## Contratos


Endpoints propuestos:

```text
POST   /auth/signup/start
GET    /auth/signup
PATCH  /auth/signup
DELETE /auth/signup
POST   /auth/signup/complete
```

Errores:

```text
EMAIL_IN_USE
SIGNUP_NOT_FOUND
SIGNUP_EXPIRED
SIGNUP_INCOMPLETE
SIGNUP_CONFLICT
```


## Pruebas obligatorias


- Migración desde vacío y desde head.
- Password nunca aparece en responses/logs.
- Expiración.
- Email duplicado activo y pending.
- Draft por pasos.
- Complete crea todos los registros.
- Error en Business revierte User.
- Repetición con misma idempotency key devuelve mismo resultado.
- Token ajeno rechazado.
- E2E PostgreSQL.
- Suite completa y Ruff.


## Criterios de aceptación


- [ ] No se crea usuario activo en start.
- [ ] Finalización es atómica.
- [ ] Contraseña queda hasheada.
- [ ] Draft sobrevive reinicio.
- [ ] Exactamente un negocio.
- [ ] Sesión activa al completar.
- [ ] Usuarios existentes siguen entrando.
- [ ] PostgreSQL y CI pasan.


## Prohibiciones


- No guardar password en frontend.
- No usar localStorage como autoridad.
- No introducir Supabase Auth.
- No borrar `/auth/register` sin migración frontend.
- No modificar demo todavía.


## Entrega del agente

1. Resumen.
2. Arquitectura encontrada.
3. Archivos modificados.
4. Migraciones y datos.
5. Contratos API/UI.
6. Seguridad.
7. Pruebas con resultados exactos.
8. Hallazgos.
9. Limitaciones.
10. Checklist marcado.



No hacer commit ni push. Dejar el working tree revisable.
