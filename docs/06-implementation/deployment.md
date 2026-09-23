---
id: IMPL-DEPLOY-001
kind: operations_spec
status: proposed
---

# Deployment

## Environments

- Local: demo provider, Docker dependencies.
- Staging: isolated database/storage, optional low-cost provider.
- Production: managed secrets, backups, monitoring, explicit provider limits.

## Build artifacts

- Web container or platform build.
- API container based on official Python image.
- Worker container only when background jobs are enabled.

## Release sequence

1. Run lint, typecheck, unit, contract, integration, and build checks.
2. Build immutable images.
3. Run database migration job.
4. Deploy API.
5. Run smoke tests.
6. Deploy web.
7. Monitor errors and provider behavior.

Before declaring a release healthy, verify `/health/live`, authenticate with a
non-production account, create a project, and fetch an authorized asset. Run
the checks from a separate browser session as well to confirm private cookies
and CORS work in the deployed topology.

## Backups

- Automated PostgreSQL backups.
- Object-storage versioning or backup policy.
- Restore test before public launch.

## Health endpoints

- `/health/live`: process alive.
- `/health/ready`: database and required dependencies available.
- Provider availability is reported separately and does not necessarily make the whole API unready.

## Secrets

- Inject through deployment secret manager.
- Never build keys into images.
- Rotate provider keys.
- Separate staging and production credentials.

## Local demo reset

The application never resets data on startup. To recreate the local demo from
a known state, run:

```bash
make demo-reset
```

The command requires its own confirmation internally, rejects
`APP_ENV=production`, and is intentionally limited to the repository-local
`hitrendy_demo.db` and `storage/`. It then runs Alembic migrations and seeds
the template catalog. It is not a production database tool.

## Production safeguards

- Set `APP_ENV=production` and use a strong, deployment-managed `JWT_SECRET`.
- Use HTTPS origins only, managed S3-compatible object storage, non-demo text
  and vision providers, and a Redis URL. The API rejects the known unsafe
  production defaults during startup.
- Configure HTTPS at the edge and set secure cookie attributes there or in the
  session deployment configuration.
- Use a managed PostgreSQL database and S3-compatible object storage; local
  storage is development-only.
- Keep `AI_PROVIDER` and `VISION_PROVIDER` explicit. The vision provider has
  separate credentials, so configuring text generation cannot send images to a
  third party.
- Apply migrations once as a release job; do not let multiple API replicas race
  to run them on startup.
# Schema migrations

The API never creates tables at application startup. Before starting an API process, run `alembic upgrade head` from `starter/backend`; the container command performs this step before starting Uvicorn. Deployments must run migrations as a single controlled operation before scaling API replicas.
