"""WAVE-009 — full account deletion journey, exercised over HTTP against real PostgreSQL.

The unit suite in ``tests/test_wave009_*.py`` runs against SQLite, which silently
accepts ``FOR UPDATE SKIP LOCKED`` without ever exercising genuine row-level
locking across concurrent connections. These tests run the same journey a real
browser and a real worker would produce, against the PostgreSQL configured by
``TEST_DATABASE_URL``: revoke access, track status publicly, purge for real,
and verify two workers racing for one job never both win it.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import get_session_factory
from app.identity import admin_cli
from app.identity.models import AccountPurgeJob, User, Workspace, WorkspaceMember
from app.identity.purge import claim_next_purge_job, process_available_purge_jobs
from app.main import app


def _status_token(seed: str) -> str:
    # 43+ base64url chars, matching the client-minted token contract.
    return (seed * 8)[:43]


async def _create_business(client: AsyncClient, workspace_id: str, *, suffix: str) -> dict:
    response = await client.post(
        "/api/v1/businesses",
        json={
            "name": f"Negocio {suffix}",
            "category": "gastronomy",
            "country": "Honduras",
            "city": "Tegucigalpa",
            "primary_product": "Café E2E",
            "target_audience": "Personas de la ciudad",
            "preferred_platforms": ["instagram"],
            "primary_objective": "sales",
        },
        headers={"X-Workspace-Id": workspace_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_full_deletion_journey_over_http_and_real_postgres(client_factory) -> None:
    client, workspace_id = await client_factory(name="Deletion E2E")
    email = (await client.get("/api/v1/auth/me")).json()["user"]["email"]
    business = await _create_business(client, workspace_id, suffix="journey")

    # The confirmation phrase must match the account's interface locale.
    account_response = await client.patch(
        "/api/v1/auth/account", json={"name": "Deletion E2E", "interface_locale": "en"}
    )
    assert account_response.status_code == 200, account_response.text
    assert account_response.json()["user"]["deletion_confirmation_phrase"] == "DELETE"

    token = _status_token(uuid.uuid4().hex)

    # A wrong confirmation phrase is rejected and access stays intact.
    wrong = await client.post(
        "/api/v1/auth/account/delete",
        json={"confirmation": "ELIMINAR", "status_token": token},
    )
    assert wrong.status_code == 422, wrong.text
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    # The correct phrase is accepted and access is revoked immediately.
    accepted = await client.post(
        "/api/v1/auth/account/delete",
        json={"confirmation": "DELETE", "status_token": token},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json()["status"] == "pending"

    # The session cookie is gone and every authenticated call now fails.
    assert (await client.get("/api/v1/auth/me")).status_code in (401, 403)
    login_attempt = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "e2e-password-segura-123"}
    )
    assert login_attempt.status_code in (401, 403), login_attempt.text

    # The public tracker works from a fresh, session-less client.
    tracker = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        missing_token = await tracker.get("/api/v1/auth/account/deletion-status")
        assert missing_token.status_code in (401, 403)

        wrong_token = await tracker.get(
            "/api/v1/auth/account/deletion-status",
            headers={"X-Deletion-Status-Token": _status_token("zzz")},
        )
        assert wrong_token.status_code in (401, 403)

        pending_status = await tracker.get(
            "/api/v1/auth/account/deletion-status",
            headers={"X-Deletion-Status-Token": token},
        )
        assert pending_status.status_code == 200, pending_status.text
        assert pending_status.json()["status"] in ("pending", "processing")
        assert pending_status.headers.get("cache-control") == "no-store"

        # Run the durable purge for real, against PostgreSQL.
        session_factory = get_session_factory()
        async with session_factory() as db:
            processed = await process_available_purge_jobs(db)
        assert processed >= 1

        completed_status = await tracker.get(
            "/api/v1/auth/account/deletion-status",
            headers={"X-Deletion-Status-Token": token},
        )
        assert completed_status.status_code == 200
        assert completed_status.json()["status"] == "completed"
    finally:
        await tracker.aclose()

    # The purge actually removed the account and its exclusive workspace.
    async with session_factory() as db:
        job = await db.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.workspace_id == workspace_id)
        )
        assert job is not None and job.status == "completed"
        remaining_user = await db.scalar(select(User).where(User.email == email.casefold()))
        assert remaining_user is None
        remaining_workspace = await db.get(Workspace, workspace_id)
        assert remaining_workspace is None

    # The freed email can be registered again — the purge was complete, not partial.
    reused = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        again = await reused.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "name": "Deletion E2E Redux",
                "password": "otra-clave-e2e-123",
                "workspace_name": "Redux Workspace",
            },
        )
        assert again.status_code == 201, again.text
    finally:
        await reused.aclose()

    del business


@pytest.mark.asyncio
async def test_two_workers_racing_for_the_same_job_only_one_claims_it(client_factory) -> None:
    """Genuine concurrency, on two independent connections, against real PostgreSQL.

    SQLite accepts ``skip_locked=True`` without any real row lock, so a unit test
    against it cannot prove this guarantee. Here two coroutines race the claim on
    two separate sessions/connections at the same time.
    """

    client, workspace_id = await client_factory(name="Race E2E")
    token = _status_token(uuid.uuid4().hex)
    delete_response = await client.post(
        "/api/v1/auth/account/delete",
        json={"confirmation": "ELIMINAR", "status_token": token},
    )
    assert delete_response.status_code == 202, delete_response.text

    session_factory = get_session_factory()
    async with session_factory() as db:
        job = await db.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.workspace_id == workspace_id)
        )
        assert job is not None and job.status == "pending"

    async def _attempt_claim() -> AccountPurgeJob | None:
        async with session_factory() as db:
            return await claim_next_purge_job(db)

    first, second = await asyncio.gather(_attempt_claim(), _attempt_claim())
    winners = [claim for claim in (first, second) if claim is not None]
    assert len(winners) == 1
    assert winners[0].id == job.id
    assert winners[0].status == "processing"


@pytest.mark.asyncio
async def test_admin_cli_retry_against_real_postgres(client_factory, monkeypatch) -> None:
    monkeypatch.setenv("HITRENDY_ADMIN_IDENTITIES", "ops@hitrendy.test")
    client, workspace_id = await client_factory(name="Admin CLI E2E")
    me = (await client.get("/api/v1/auth/me")).json()["user"]
    token = _status_token(uuid.uuid4().hex)
    delete_response = await client.post(
        "/api/v1/auth/account/delete",
        json={"confirmation": "ELIMINAR", "status_token": token},
    )
    assert delete_response.status_code == 202, delete_response.text

    session_factory = get_session_factory()
    async with session_factory() as db:
        status_outcome = await admin_cli.execute(
            db,
            action="status",
            user_id=me["id"],
            actor="ops@hitrendy.test",
            reason="verificación e2e",
            confirm="",
        )
        assert status_outcome.ok and status_outcome.message == "pending"

        retry_outcome = await admin_cli.execute(
            db,
            action="retry",
            user_id=me["id"],
            actor="ops@hitrendy.test",
            reason="purga inmediata e2e",
            confirm="RETRY",
        )
        assert retry_outcome.ok and retry_outcome.message == "completed"

        remaining_workspace = await db.get(Workspace, workspace_id)
        assert remaining_workspace is None
        remaining_membership = await db.scalar(
            select(WorkspaceMember).where(WorkspaceMember.user_id == me["id"])
        )
        assert remaining_membership is None
