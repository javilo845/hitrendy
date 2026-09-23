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
