---
id: API-HTTP-001
kind: api_spec
status: accepted
related: [ARCH-BACKEND-001]
---

# HTTP API

Base path: `/api/v1`

## Conventions

- JSON request and response bodies.
- UUID-like opaque IDs.
- ISO 8601 timestamps in UTC.
- Cursor pagination for conversations, projects, and assets.
- Stable error envelope.
- `Idempotency-Key` para generación; la finalización de carga usa una sesión de
  carga de un solo uso.

En `POST /conversations/{conversation_id}/messages`, la clave se limita al
workspace, endpoint y payload. Repetirla con el mismo payload devuelve la
respuesta persistida; repetirla con otro payload devuelve `409 CONFLICT`. Una
solicitud concurrente con la misma clave queda reservada una sola vez y las
repeticiones reciben un error recuperable hasta que el resultado esté listo.

## Identity

### `POST /auth/login`

Authenticate and set secure session cookie.

### `POST /auth/logout`

Invalidate current session.

### `GET /me`

Return user and workspace summary.

### `POST /auth/register`

Creates a user, an owner workspace membership, and an HttpOnly session cookie.
When `BETA_INVITES_ENABLED=1`, the request must include the one-time
`invite_code` associated with the email.

### `POST /auth/password-reset/request`

Accepts an email and always returns `202` with the same generic message. A
configured email adapter may deliver a one-time link; the token is hashed in
the database and never returned by the API.

### `POST /auth/password-reset/confirm`

Accepts `token` and a new password. A successful reset revokes all existing
sessions; expired or reused links are rejected.

### Session scope

All private endpoints require the session cookie. `X-Workspace-Id` is optional and can only select a workspace to which the current session already belongs; it is never accepted as proof of identity.

## Business profile

### `POST /businesses`

Creates a business from onboarding.

### `GET /businesses/{business_id}`

Returns authorized business details.

### `PATCH /businesses/{business_id}`

Partial update with optimistic version field.

### `PUT /businesses/{business_id}/brand-profile`

Create or replace approved brand profile version.

## Conversations

### `POST /conversations`

```json
{
  "business_id": "biz_123",
  "title": "Promoción bebida fría"
}
```

### `GET /conversations`

Filters: `business_id`, `status` (`active` or `archived`) and `search`.
Each row includes a compact `last_message` preview.

### `PATCH /conversations/{conversation_id}`

Renames a conversation or changes its status between `active` and `archived`.
The operation is workspace-authorized and archived conversations reject new messages
until restored.

### `GET /conversations/{conversation_id}`

Returns thread metadata and paginated messages.

### `POST /conversations/{conversation_id}/messages`

```json
{
  "text": "Quiero promocionar una bebida fría esta semana",
  "ui_intent": "create_social_post",
  "platform": "instagram",
  "tone": "youthful",
  "attachment_ids": []
}
```

`ui_intent` admite `create_social_post` (valor por defecto) y
`create_short_video_script`. El segundo devuelve un borrador estructurado con
hook, duración, escenas, texto en pantalla, locución, CTA y caption.
`analyze_visual` exige exactamente un elemento en `attachment_ids`, lo analiza
con el proveedor de visión autorizado y devuelve una revisión estructurada. Las
demás acciones se rechazan explícitamente; no se reinterpretan como publicaciones.

## Generation

### `POST /artifacts/{artifact_id}/variations`

```json
{
  "transformation": "more_youthful",
  "notes": "Mantén el llamado a visitar el local"
}
```

### `PATCH /artifacts/{artifact_id}/versions/{version_id}`

Persist user edits.

## Projects

### `POST /projects`

Create from artifact or template.

### `GET /projects`

List active or archived projects.

### `GET /projects/{project_id}`

Project with current artifact and version summary.

### `PATCH /projects/{project_id}`

Rename, archive, or update metadata.

### `POST /projects/{project_id}/duplicate`

Creates a new active project in the same authorized workspace from an existing project.

### `GET /projects/{project_id}/export`

Returns the current project and latest editable content as `hitrendy-project/v1` JSON.

### `GET /projects/{project_id}/versions`

Lists authorized project version metadata, newest first.

### `POST /projects/{project_id}/versions/{version_id}/restore`

Promotes an earlier authorized version by creating a new current version. It
never overwrites or deletes historical content, and rejects the already-current
version.

## Templates

### `GET /templates`

Filters: platform, format, category, objective, search.

### `GET /templates/{template_id}`

Returns preview and editable slots.

### `POST /templates/recommendations`

Returns ranked internal templates with an explicit rationale for platform, objective and optional category.

## Assets

### `POST /assets/uploads`

Request an upload session. The current API finalizes through its protected
endpoint; a storage provider may use the same session to implement a direct
upload target later.

### `POST /assets/uploads/{upload_id}/complete`

Finalize and validate uploaded object.

### `POST /assets/{asset_id}/analyses`

Run visual review.

### `GET /assets`

List authorized library assets.

### `GET /assets/{asset_id}/content`

Streams the authorized image with a private, short-lived cache policy. Object
storage keys and permanent public URLs are never exposed to the browser.

## Feedback

### `GET /policies`

Public versions and paths for privacy, terms and support. It also reports the
configured retention period, email-verification decision and closed-beta flag.

### `POST /feedback`

Authenticated product/support feedback. Accepts `category`, `message` and an
optional rating. `Idempotency-Key` makes a repeated submission return the
original feedback row for that workspace.

### `POST /abuse/reports`

Authenticated abuse report with a bounded category, message and optional
resource id. It creates a moderation queue record; it does not publish or
delete content automatically.

### `POST /conversations/artifacts/{artifact_id}/feedback`

```json
{
  "rating": "useful",
  "reason": null
}
```
