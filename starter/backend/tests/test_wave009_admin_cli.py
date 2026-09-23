"""WAVE-009: audited administration of purge jobs through the CLI.

Every test drives the real entrypoint ``admin_cli.run(argv)``. The command opens
its own session factory, so it runs in a worker thread with an engine bound to
the same test database file.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.dependencies import get_db
from app.identity import admin_cli
from app.identity.models import (
    AccountPurgeJob,
    AdminAuditEvent,
    User,
    Workspace,
    WorkspaceMember,
)
from app.main import app

from .conftest import TEST_DB_URL

ADMIN = "ops@hitrendy.test"
INTRUDER = "curioso@example.com"
REASON = "solicitud de soporte 4821"


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    generator = app.dependency_overrides[get_db]()
    session = await generator.__anext__()
    try:
        yield session
    finally:
        await generator.aclose()


def _cli_session_factory() -> async_sessionmaker[AsyncSession]:
    """A factory the CLI can use inside its own event loop."""

    engine = create_async_engine(TEST_DB_URL, poolclass=NullPool)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class FakeStorage:
    """The purge triggered by ``retry`` must not touch a real provider."""

    async def delete(self, *, key: str) -> None:
        del key

    async def exists(self, *, key: str) -> bool:
        del key
        return False


@pytest.fixture(autouse=True)
def cli_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(admin_cli.ALLOWLIST_ENV, f"{ADMIN}, otro-operador@hitrendy.test")
    monkeypatch.setattr(admin_cli, "get_session_factory", _cli_session_factory)
    monkeypatch.setattr(
        "app.identity.purge.get_object_storage_provider", lambda: FakeStorage()
    )


async def run_cli(*argv: str) -> int:
    """Run the CLI the way an operator would, off the test event loop."""

    return await asyncio.to_thread(admin_cli.run, list(argv))


async def _seed_job(
    *, suffix: str, status: str = "pending", started_at: datetime | None = None
) -> str:
    async with session_scope() as session:
        user = User(
            id=f"usr_{suffix}",
            email=f"{suffix}@example.com",
            name="Cuenta en eliminación",
            password_hash="scrypt$00$00",
            status="deletion_pending",
            deletion_requested_at=datetime.now(UTC),
        )
        workspace = Workspace(id=f"ws_{suffix}", name=f"Workspace {suffix}")
        session.add_all(
            [
                user,
                workspace,
                WorkspaceMember(
                    id=f"wsm_{suffix}",
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role="owner",
                ),
                AccountPurgeJob(
                    id=f"job_{suffix}",
                    user_id=user.id,
                    workspace_id=workspace.id,
                    status=status,
                    started_at=started_at,
                    next_attempt_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()
    return f"usr_{suffix}"


async def _job_status(user_id: str) -> str | None:
    async with session_scope() as session:
        job = await session.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.user_id == user_id)
        )
        return job.status if job is not None else None


async def _audit(user_id: str) -> list[AdminAuditEvent]:
    async with session_scope() as session:
        rows = await session.execute(
            select(AdminAuditEvent)
            .where(AdminAuditEvent.target_user_id == user_id)
            .order_by(AdminAuditEvent.created_at)
        )
        return list(rows.scalars().all())


@pytest.mark.asyncio
async def test_status_reports_the_job_for_an_allowlisted_actor(client, capsys) -> None:
    user_id = await _seed_job(suffix="cli_status")

    exit_code = await run_cli(
        "status", "--user-id", user_id, "--actor", ADMIN, "--reason", REASON
    )

    assert exit_code == 0
    assert "pending" in capsys.readouterr().out
    assert await _job_status(user_id) == "pending"


@pytest.mark.asyncio
async def test_a_non_allowlisted_actor_is_rejected_and_audited(client) -> None:
    user_id = await _seed_job(suffix="cli_intruder")

    exit_code = await run_cli(
        "retry",
        "--user-id",
        user_id,
        "--actor",
        INTRUDER,
        "--reason",
        REASON,
        "--confirm",
        "RETRY",
    )

    assert exit_code == 2
    # Nothing happened to the job, and the attempt is attributable.
    assert await _job_status(user_id) == "pending"
    events = await _audit(user_id)
    assert [event.result for event in events] == [admin_cli.DENIED_NOT_AUTHORIZED]
    assert events[0].actor == INTRUDER
    assert events[0].action == "retry"


@pytest.mark.asyncio
async def test_an_empty_allowlist_authorizes_nobody(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(admin_cli.ALLOWLIST_ENV, raising=False)
    user_id = await _seed_job(suffix="cli_no_allowlist")

    exit_code = await run_cli(
        "status", "--user-id", user_id, "--actor", ADMIN, "--reason", REASON
    )

    assert exit_code == 2
    assert [event.result for event in await _audit(user_id)] == [
        admin_cli.DENIED_NOT_AUTHORIZED
    ]


@pytest.mark.asyncio
async def test_actor_and_reason_are_mandatory(client) -> None:
    user_id = await _seed_job(suffix="cli_mandatory")

    with pytest.raises(SystemExit) as missing_actor:
        await run_cli("status", "--user-id", user_id, "--reason", REASON)
    assert missing_actor.value.code == 2

    with pytest.raises(SystemExit) as missing_reason:
        await run_cli("status", "--user-id", user_id, "--actor", ADMIN)
    assert missing_reason.value.code == 2

    # A blank motive is refused before anything is attributed to the actor.
    assert (
        await run_cli("status", "--user-id", user_id, "--actor", ADMIN, "--reason", "   ")
        == 2
    )
    assert await _audit(user_id) == []


@pytest.mark.asyncio
async def test_mutating_actions_require_the_explicit_confirmation(client) -> None:
    user_id = await _seed_job(suffix="cli_confirm", status="failed")

    assert (
        await run_cli("retry", "--user-id", user_id, "--actor", ADMIN, "--reason", REASON)
        == 2
    )
    assert (
        await run_cli(
            "reset",
            "--user-id",
            user_id,
            "--actor",
            ADMIN,
            "--reason",
            REASON,
            "--confirm",
            "RETRY",
        )
        == 2
    )

    assert await _job_status(user_id) == "failed"
    assert [event.result for event in await _audit(user_id)] == [
        admin_cli.DENIED_CONFIRMATION,
        admin_cli.DENIED_CONFIRMATION,
    ]


@pytest.mark.asyncio
async def test_retry_finishes_the_purge_and_is_idempotent(client) -> None:
    user_id = await _seed_job(suffix="cli_retry", status="failed")

    first = await run_cli(
        "retry",
        "--user-id",
        user_id,
        "--actor",
        ADMIN,
        "--reason",
        REASON,
        "--confirm",
        "RETRY",
    )
    assert first == 0
    assert await _job_status(user_id) == "completed"

    async with session_scope() as session:
        assert await session.get(User, user_id) is None
        assert await session.get(Workspace, "ws_cli_retry") is None

    # Repeating the command reports the terminal status without redoing work.
    second = await run_cli(
        "retry",
        "--user-id",
        user_id,
        "--actor",
        ADMIN,
        "--reason",
        REASON,
        "--confirm",
        "RETRY",
    )
    assert second == 0
    assert await _job_status(user_id) == "completed"
    assert [event.result for event in await _audit(user_id)] == [
        "ok:completed",
        "ok:completed",
    ]


@pytest.mark.asyncio
async def test_reset_requeues_an_abandoned_job_without_reactivating_the_account(
    client,
) -> None:
    user_id = await _seed_job(
        suffix="cli_reset",
        status="processing",
        started_at=datetime.now(UTC) - timedelta(hours=2),
    )

    exit_code = await run_cli(
        "reset",
        "--user-id",
        user_id,
        "--actor",
        ADMIN,
        "--reason",
        REASON,
        "--confirm",
        "RESET",
    )

    assert exit_code == 0
    async with session_scope() as session:
        job = await session.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.user_id == user_id)
        )
        assert job is not None
        assert job.status == "pending"
        assert job.started_at is None
        assert job.last_error is None
        # The account stays blocked: a reset never brings an account back.
        user = await session.get(User, user_id)
        assert user is not None
        assert user.status == "deletion_pending"
        assert user.deletion_requested_at is not None


@pytest.mark.asyncio
async def test_reset_refuses_a_completed_job(client) -> None:
    user_id = await _seed_job(suffix="cli_reset_done", status="completed")

    exit_code = await run_cli(
        "reset",
        "--user-id",
        user_id,
        "--actor",
        ADMIN,
        "--reason",
        REASON,
        "--confirm",
        "RESET",
    )

    assert exit_code == 2
    assert await _job_status(user_id) == "completed"
    assert [event.result for event in await _audit(user_id)] == [
        admin_cli.DENIED_INVALID_STATE
    ]


@pytest.mark.asyncio
async def test_an_unknown_target_is_denied_and_audited(client) -> None:
    exit_code = await run_cli(
        "status", "--user-id", "usr_does_not_exist", "--actor", ADMIN, "--reason", REASON
    )

    assert exit_code == 2
    events = await _audit("usr_does_not_exist")
    assert [event.result for event in events] == [admin_cli.DENIED_NOT_FOUND]
    assert events[0].target_workspace_id is None


@pytest.mark.asyncio
async def test_the_audit_trail_records_the_action_without_any_secret(client) -> None:
    user_id = await _seed_job(suffix="cli_audit")
    before = datetime.now(UTC) - timedelta(seconds=5)

    assert (
        await run_cli(
            "status", "--user-id", user_id, "--actor", ADMIN.upper(), "--reason", REASON
        )
        == 0
    )

    events = await _audit(user_id)
    assert len(events) == 1
    event = events[0]
    assert event.actor == ADMIN  # normalized, so the allowlist stays comparable
    assert event.action == "status"
    assert event.reason == REASON
    assert event.target_workspace_id == "ws_cli_audit"
    assert event.result == "ok:pending"
    created_at = event.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    assert created_at >= before
    # The trail carries no token, cookie, key or stack trace.
    assert set(event.__dict__) & {"token", "cookie", "password", "traceback"} == set()
