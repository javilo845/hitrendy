---
id: API-REALTIME-001
kind: api_spec
status: proposed
---

# Realtime events

Realtime behavior is optional for the first working slice. When enabled, use Server-Sent Events for one-way generation progress.

Endpoint:

```text
GET /api/v1/generation-jobs/{job_id}/events
```

## Event types

### `job.status`

```json
{"phase":"context","message":"Revisando tu perfil de marca…"}
```

### `job.partial`

Contains a complete validated section, never hidden reasoning or raw tokens.

### `job.completed`

```json
{"artifact_id":"art_123","version_id":"ver_1"}
```

### `job.failed`

```json
{"code":"GENERATION_PROVIDER_UNAVAILABLE","retryable":true}
```

## Rules

- Authenticate the stream.
- Verify job ownership.
- Heartbeat every 15–30 seconds.
- Persist terminal state before emission.
- Client reconnects using last event ID.
