---
id: ARCH-BACKEND-001
kind: architecture_spec
status: accepted
related: [ARCH-CONTEXT-001, API-HTTP-001, AI-ORCH-001]
---

# Backend architecture

## Stack

- Python 3.12+.
- FastAPI.
- Pydantic v2 models.
- SQLAlchemy 2.x.
- Alembic migrations.
- PostgreSQL production; SQLite only for offline demo/tests where appropriate.
- Redis for rate limits, short cache, and job coordination.
- S3-compatible storage for media.

## Package layout

```text
app/
├── main.py
├── core/
│   ├── config.py
│   ├── security.py
│   ├── logging.py
│   └── errors.py
├── identity/
├── business/
├── conversations/
├── generation/
├── templates/
├── projects/
├── library/
├── analytics/
├── providers/
│   ├── ai/
│   ├── storage/
│   └── auth/
└── db/
    ├── session.py
    ├── base.py
    └── migrations/
```

Each module contains domain models, application services, repository ports, HTTP routes, and adapter implementations as needed.

## Application service example

```python
class GenerateArtifactService:
    def __init__(
        self,
        business_repo: BusinessRepository,
        conversation_repo: ConversationRepository,
        artifact_repo: ArtifactRepository,
        provider: ContentModelProvider,
        evaluator: ArtifactEvaluator,
    ) -> None:
        ...

    async def execute(self, command: GenerateArtifactCommand) -> GeneratedArtifact:
        profile = await self.business_repo.get_generation_profile(
            workspace_id=command.workspace_id,
            business_id=command.business_id,
        )
        request = build_model_request(profile=profile, command=command)
        draft = await self.provider.generate(request)
        artifact = validate_and_normalize(draft)
        evaluation = self.evaluator.evaluate(artifact, request)
        if not evaluation.accepted:
            artifact = await self.provider.repair(request, artifact, evaluation)
        return await self.artifact_repo.save(artifact)
```

## Error model

All public errors use a stable envelope:

```json
{
  "error": {
    "code": "GENERATION_PROVIDER_UNAVAILABLE",
    "message": "No pudimos generar el contenido en este momento.",
    "retryable": true,
    "request_id": "req_..."
  }
}
```

No stack traces, SQL details, or provider payloads reach the client.

## Authorization

Every workspace-owned query includes `workspace_id`. Business, project, asset, conversation, and artifact IDs must be validated against ownership before read or write.

## Upload pipeline

1. Validate declared type and actual content signature.
2. Enforce size and pixel limits.
3. Generate server-side object key.
4. Store outside the web root.
5. Record metadata and owner.
6. Optionally scan before AI analysis.
7. Provide signed, expiring access URLs.

## Idempotency

La generación conversacional admite `Idempotency-Key`. Las solicitudes repetidas
del mismo workspace, endpoint y clave devuelven el resultado original ya
persistido. La finalización de cargas se protege mediante una sesión de carga de
un solo uso.

## Observability

Every request records:

- request ID,
- route,
- workspace ID hash or safe identifier,
- latency,
- status,
- provider name,
- model name,
- token/cost metrics when available,
- validation and retry outcome.

Do not log complete prompts, passwords, provider keys, or user-uploaded files.
