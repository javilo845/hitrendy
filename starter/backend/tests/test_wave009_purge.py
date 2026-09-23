"""WAVE-009 — durable account purge, workspace safety and worker semantics."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.assets.models import Asset, AssetAnalysis, UploadSession
from app.business.models import BrandProfile, Business
from app.conversations.models import (
    AIUsageEvent,
    ArtifactEvent,
    ArtifactFeedback,
    ArtifactVersion,
    Conversation,
    GeneratedArtifact,
    IdempotencyRecord,
    Message,
)
from app.dependencies import get_db
from app.identity.account_deletion import (
    WORKSPACE_INCLUDED,
    WORKSPACE_MULTIPLE,
    WORKSPACE_NOT_OWNER,
    WORKSPACE_SHARED,
    decide_purgeable_workspace,
)
from app.identity.models import (
    AccountPurgeJob,
    AdminAuditEvent,
    AuthSession,
    OAuthAccount,
    PendingSignup,
    User,
    UserPreference,
    Workspace,
    WorkspaceMember,
)
from app.identity.purge import (
    STUCK_PROCESSING_AFTER,
    claim_next_purge_job,
    execute_purge,
    process_available_purge_jobs,
    recover_stuck_jobs,
    run_account_purge,
)
from app.identity.purge_worker import run_once
from app.main import app
from app.projects.models import CreationFlowEvent, Project
from app.templates.models import Template
from app.trends.models import TrendItem, WorkspaceTrendRelevance


@asynccontextmanager
async def session_scope() -> AsyncIterator:
    generator = app.dependency_overrides[get_db]()
    session = await generator.__anext__()
    try:
        yield session
    finally:
        await generator.aclose()


class FakeStorage:
    """Deterministic object storage: records every call, fails on request."""

    def __init__(self, *, failing_keys: set[str] | None = None) -> None:
        self.objects: set[str] = set()
        self.failing_keys = failing_keys or set()
        self.delete_calls: list[str] = []

    async def delete(self, *, key: str) -> None:
        self.delete_calls.append(key)
        if key in self.failing_keys:
            raise RuntimeError("provider-secret=must-not-leak")
        self.objects.discard(key)

    async def exists(self, *, key: str) -> bool:
        return key in self.objects


async def _make_account(
    session,
    *,
    suffix: str,
    email: str | None = None,
    workspace_id: str | None = None,
    role: str = "owner",
) -> tuple[User, Workspace]:
    user = User(
        id=f"usr_{suffix}",
        email=email or f"{suffix}@example.com",
        name=f"User {suffix}",
        password_hash="scrypt$00$00",
    )
    session.add(user)
    if workspace_id is None:
        workspace = Workspace(id=f"ws_{suffix}", name=f"Workspace {suffix}")
        session.add(workspace)
    else:
        workspace = await session.get(Workspace, workspace_id)
        assert workspace is not None
    session.add(
        WorkspaceMember(
            id=f"wsm_{suffix}_{workspace.id}",
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
        )
    )
    await session.commit()
    return user, workspace


async def _seed_workspace_content(session, workspace: Workspace, *, suffix: str) -> None:
    """One representative row in every workspace-scoped table."""

    business = Business(
        id=f"biz_{suffix}",
        workspace_id=workspace.id,
        name="Negocio",
        category="gastronomy",
        country="Honduras",
        city="Tegucigalpa",
        primary_product="Café",
        target_audience="Vecinos",
        preferred_platforms='["instagram"]',
        primary_objective="sales",
    )
    session.add(business)
    session.add(
        BrandProfile(
            id=f"brand_{suffix}",
            business_id=business.id,
            voice_tones='["friendly"]',
            value_proposition="Café artesanal.",
        )
    )
    conversation = Conversation(
        id=f"cnv_{suffix}",
        workspace_id=workspace.id,
        business_id=business.id,
        title="Conversación",
    )
    session.add(conversation)
    session.add(
        Message(
            id=f"msg_{suffix}",
            conversation_id=conversation.id,
            role="user",
            content="Hola",
        )
    )
    project = Project(
        id=f"prj_{suffix}",
        workspace_id=workspace.id,
        business_id=business.id,
        name="Proyecto",
        platform="instagram",
    )
    session.add(project)
    # Artifacts are reachable through a conversation *and* through a project.
    for artifact_id, parent in ((f"art_c_{suffix}", conversation), (f"art_p_{suffix}", project)):
        session.add(
            GeneratedArtifact(
                id=artifact_id,
                conversation_id=conversation.id if parent is conversation else None,
                project_id=project.id if parent is project else None,
                artifact_type="caption",
                platform="instagram",
                objective="sales",
                business_profile_version=1,
            )
        )
        session.add(
            ArtifactVersion(
                id=f"ver_{artifact_id}",
                artifact_id=artifact_id,
                version_number=1,
                content_json="{}",
            )
        )
        session.add(
            ArtifactFeedback(id=f"fbk_{artifact_id}", artifact_id=artifact_id, rating="up")
        )
        session.add(
            ArtifactEvent(id=f"evt_{artifact_id}", artifact_id=artifact_id, event_type="copied")
        )
    session.add(
        CreationFlowEvent(
            id=f"flow_{suffix}",
            workspace_id=workspace.id,
            business_id=business.id,
            flow_started_at=datetime.now(UTC),
            completion_status="completed",
        )
    )
    session.add(
        AIUsageEvent(
            id=f"usg_{suffix}",
            workspace_id=workspace.id,
            capability="text",
            quality_level="standard",
            provider="fake",
            requested_model="fake-model",
            outcome="success",
        )
    )
    session.add(
        IdempotencyRecord(
            id=f"idm_{suffix}",
            workspace_id=workspace.id,
            endpoint="/messages",
            key=f"key-{suffix}",
            payload_hash="0" * 64,
            status="completed",
        )
    )
    session.add(
        UploadSession(
            id=f"upl_{suffix}",
            workspace_id=workspace.id,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    asset = Asset(
        id=f"ast_{suffix}",
        workspace_id=workspace.id,
        original_name="foto.png",
        storage_path=f"accounts/{suffix}/foto.png",
        mime_type="image/png",
        file_size_bytes=10,
    )
    session.add(asset)
    session.add(
        AssetAnalysis(
            id=f"ana_{suffix}",
            asset_id=asset.id,
            summary="Resumen",
            strengths_json="[]",
            improvements_json="[]",
        )
    )
    await session.commit()


async def _create_job(session, user: User, workspace_id: str | None) -> AccountPurgeJob:
    user.status = "deletion_pending"
    user.deletion_requested_at = datetime.now(UTC)
    job = AccountPurgeJob(
        id=f"job_{user.id}",
        user_id=user.id,
        workspace_id=workspace_id,
        status="pending",
    )
    session.add(job)
    await session.commit()
    return job


async def _count(session, table: str, column: str, value: str) -> int:
    return int(
        await session.scalar(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :value"), {"value": value}
        )
    )


@pytest.mark.asyncio
async def test_purge_removes_every_workspace_scoped_row(client, monkeypatch) -> None:
    storage = FakeStorage()
    monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: storage)
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="purge_all")
        await _seed_workspace_content(session, workspace, suffix="purge_all")
        storage.objects.add("accounts/purge_all/foto.png")
        session.add(UserPreference(user_id=user.id, interface_locale="es"))
        session.add(
            AuthSession(
                id="ses_purge_all",
                token_hash="a" * 64,
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add(
            OAuthAccount(
                id="oau_purge_all",
                user_id=user.id,
                provider="google",
                provider_subject="sub-purge-all",
                email_at_link_time="purge_all@example.com",
            )
        )
        session.add(
            PendingSignup(
                id="pen_purge_all",
                token_hash="b" * 64,
                email_normalized="purge_all@example.com",
                name="User",
                password_hash="scrypt$00$00",
                draft_json="{}",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.add(
            AdminAuditEvent(
                id="aud_keep",
                actor="ops@hitrendy",
                action="status",
                target_user_id=user.id,
                reason="soporte",
                result="ok:pending",
            )
        )
        session.add(
            Template(
                id="tpl_global_keep",
                title="Plantilla global",
                platforms='["instagram"]',
                formats='["post"]',
                category="gastronomy",
                objective="sales",
                thumbnail_url="https://example.com/t.png",
                editable_slots="[]",
            )
        )
        await session.commit()

        # A second account keeps its own workspace and rows untouched.
        other_user, other_workspace = await _make_account(session, suffix="purge_other")
        await _seed_workspace_content(session, other_workspace, suffix="purge_other")

        job = await _create_job(session, user, workspace.id)
        completed = await run_account_purge(session, job)
        assert completed.status == "completed"

        for table, column in (
            ("conversations", "workspace_id"),
            ("projects", "workspace_id"),
            ("creation_flow_events", "workspace_id"),
            ("ai_usage_events", "workspace_id"),
            ("idempotency_records", "workspace_id"),
            ("upload_sessions", "workspace_id"),
            ("assets", "workspace_id"),
            ("businesses", "workspace_id"),
        ):
            assert await _count(session, table, column, workspace.id) == 0, table
            assert await _count(session, table, column, other_workspace.id) == 1, table
        # Rows reachable only through a conversation *or* a project are gone,
        # and the untouched account keeps exactly the same rows it had.
        assert await session.get(Message, "msg_purge_all") is None
        assert await session.get(Message, "msg_purge_other") is not None
        for prefix in ("art_c", "art_p"):
            assert await session.get(GeneratedArtifact, f"{prefix}_purge_all") is None
            assert await session.get(GeneratedArtifact, f"{prefix}_purge_other") is not None
            assert await session.get(ArtifactVersion, f"ver_{prefix}_purge_all") is None
            assert await session.get(ArtifactVersion, f"ver_{prefix}_purge_other") is not None
            assert await session.get(ArtifactFeedback, f"fbk_{prefix}_purge_all") is None
            assert await session.get(ArtifactFeedback, f"fbk_{prefix}_purge_other") is not None
            assert await session.get(ArtifactEvent, f"evt_{prefix}_purge_all") is None
            assert await session.get(ArtifactEvent, f"evt_{prefix}_purge_other") is not None
        assert await _count(session, "brand_profiles", "business_id", "biz_purge_all") == 0
        assert await _count(session, "asset_analyses", "asset_id", "ast_purge_all") == 0

        assert await session.get(User, user.id) is None
        assert await session.get(Workspace, workspace.id) is None
        assert await session.get(UserPreference, user.id) is None
        assert (
            await session.scalar(
                select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OAuthAccount)
                .where(OAuthAccount.user_id == user.id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PendingSignup)
                .where(PendingSignup.email_normalized == "purge_all@example.com")
            )
            == 0
        )
        # Global and administrative data survive.
        assert await session.get(Template, "tpl_global_keep") is not None
        assert await session.get(AdminAuditEvent, "aud_keep") is not None
        assert await session.get(User, other_user.id) is not None
        assert storage.objects == set()


@pytest.mark.asyncio
async def test_purge_removes_private_trend_relevance_but_keeps_global_evidence(client) -> None:
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="purge_trends")
        item = TrendItem(
            id="trend_global_keep",
            group_key="g" * 64,
            observation_window="utc-week-v1:0",
            fingerprint="f" * 64,
            title="Tendencia global",
            summary="Resumen",
            region="HN",
            category="gastronomy",
            observed_at=datetime.now(UTC),
            freshness_score=0.5,
            scoring_version="trend-v1",
            component_scores="{}",
            total_score=0.5,
            calculated_at=datetime.now(UTC),
        )
        session.add_all((item, WorkspaceTrendRelevance(
            workspace_id=workspace.id, trend_item_id=item.id, score=0.5,
            relevance_version="workspace-relevance-v1", component_scores="{}", calculated_at=datetime.now(UTC),
        )))
        await session.commit()
        completed = await run_account_purge(session, await _create_job(session, user, workspace.id))
        assert completed.status == "completed"
        assert await session.get(TrendItem, item.id) is not None
        assert await _count(session, "workspace_trend_relevance", "workspace_id", workspace.id) == 0


@pytest.mark.asyncio
async def test_purge_keeps_a_shared_workspace_and_the_other_member_data(client) -> None:
    async with session_scope() as session:
        owner, workspace = await _make_account(session, suffix="shared_owner")
        await _seed_workspace_content(session, workspace, suffix="shared_owner")
        member, _ = await _make_account(
            session, suffix="shared_member", workspace_id=workspace.id, role="editor"
        )

        decision = await decide_purgeable_workspace(session, owner.id)
        assert decision.reason == WORKSPACE_SHARED
        assert decision.workspace_id is None

        job = await _create_job(session, owner, decision.workspace_id)
        completed = await run_account_purge(session, job)
        assert completed.status == "completed"

        assert await session.get(User, owner.id) is None
        # The shared workspace, its content and the other member are intact.
        assert await session.get(Workspace, workspace.id) is not None
        assert await session.get(User, member.id) is not None
        assert await _count(session, "conversations", "workspace_id", workspace.id) == 1
        assert await _count(session, "assets", "workspace_id", workspace.id) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.workspace_id == workspace.id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_workspace_decision_refuses_multiple_workspaces_and_non_owners(client) -> None:
    async with session_scope() as session:
        user, first = await _make_account(session, suffix="multi_one")
        second = Workspace(id="ws_multi_two", name="Segundo")
        session.add(second)
        session.add(
            WorkspaceMember(
                id="wsm_multi_two", workspace_id=second.id, user_id=user.id, role="owner"
            )
        )
        await session.commit()
        decision = await decide_purgeable_workspace(session, user.id)
        assert decision.reason == WORKSPACE_MULTIPLE and decision.workspace_id is None

        guest, host = await _make_account(session, suffix="guest_host")
        await session.execute(
            text("UPDATE workspace_members SET role = 'editor' WHERE user_id = :uid"),
            {"uid": guest.id},
        )
        await session.commit()
        guest_decision = await decide_purgeable_workspace(session, guest.id)
        assert guest_decision.reason == WORKSPACE_NOT_OWNER and guest_decision.workspace_id is None

        # And the happy path still includes an exclusively owned workspace.
        solo, solo_workspace = await _make_account(session, suffix="solo_owner")
        solo_decision = await decide_purgeable_workspace(session, solo.id)
        assert solo_decision.reason == WORKSPACE_INCLUDED
        assert solo_decision.workspace_id == solo_workspace.id
        assert first.id != second.id and host.id


@pytest.mark.asyncio
async def test_storage_failure_keeps_the_account_blocked_and_retry_finishes_the_job(
    client, monkeypatch, caplog
) -> None:
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="retry_storage")
        first = Asset(
            id="ast_retry_a",
            workspace_id=workspace.id,
            original_name="a.png",
            storage_path="accounts/retry/a.png",
            mime_type="image/png",
            file_size_bytes=1,
        )
        second = Asset(
            id="ast_retry_b",
            workspace_id=workspace.id,
            original_name="b.png",
            storage_path="accounts/retry/b.png",
            mime_type="image/png",
            file_size_bytes=1,
        )
        session.add_all([first, second])
        await session.commit()

        storage = FakeStorage(failing_keys={"accounts/retry/b.png"})
        storage.objects.update({"accounts/retry/a.png", "accounts/retry/b.png"})
        monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: storage)

        job = await _create_job(session, user, workspace.id)
        with caplog.at_level(logging.WARNING, logger="hitrendy.purge"):
            failed = await run_account_purge(session, job)
        assert failed.status == "failed"
        assert failed.last_error == "No se pudo completar la purga de recursos."
        # Nothing from the provider message reaches the logs or the job row.
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert "provider-secret" not in logged and "provider-secret" not in failed.last_error
        assert "provider-secret" not in (failed.last_error or "")

        # A stayed deleted, B is still there, and the account is still blocked.
        assert storage.objects == {"accounts/retry/b.png"}
        assert await session.get(Asset, "ast_retry_a") is None
        assert await session.get(Asset, "ast_retry_b") is not None
        blocked = await session.get(User, user.id)
        assert blocked is not None and blocked.status == "deletion_pending"

        storage.failing_keys.clear()
        storage.delete_calls.clear()
        failed.next_attempt_at = datetime.now(UTC)
        await session.commit()
        completed = await run_account_purge(session, failed)
        assert completed.status == "completed"
        # The retry only touches what is left: no repeated destructive call on A.
        assert storage.delete_calls == ["accounts/retry/b.png"]
        assert storage.objects == set()
        assert await session.get(User, user.id) is None


@pytest.mark.asyncio
async def test_missing_object_counts_as_already_deleted(client, monkeypatch) -> None:
    class MissingObjectStorage(FakeStorage):
        async def delete(self, *, key: str) -> None:
            self.delete_calls.append(key)
            raise RuntimeError("404 object not found")

    storage = MissingObjectStorage()
    monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: storage)
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="already_gone")
        session.add(
            Asset(
                id="ast_gone",
                workspace_id=workspace.id,
                original_name="gone.png",
                storage_path="accounts/gone.png",
                mime_type="image/png",
                file_size_bytes=1,
            )
        )
        await session.commit()
        job = await _create_job(session, user, workspace.id)
        completed = await run_account_purge(session, job)
        assert completed.status == "completed"
        assert await session.get(Asset, "ast_gone") is None


@pytest.mark.asyncio
async def test_completed_job_survives_the_user_and_workspace_it_deleted(
    client, monkeypatch
) -> None:
    monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: FakeStorage())
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="survivor")
        job = await _create_job(session, user, workspace.id)
        job_id = job.id
        completed = await run_account_purge(session, job)
        assert completed.status == "completed"
        session.expunge_all()
        surviving = await session.get(AccountPurgeJob, job_id)
        assert surviving is not None
        assert surviving.status == "completed" and surviving.completed_at is not None
        assert surviving.workspace_id == workspace.id
        assert await session.get(Workspace, workspace.id) is None


@pytest.mark.asyncio
async def test_stuck_processing_job_is_recovered_and_claimable_again(client) -> None:
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="stuck")
        job = await _create_job(session, user, workspace.id)
        job.status = "processing"
        job.started_at = datetime.now(UTC) - STUCK_PROCESSING_AFTER - timedelta(minutes=1)
        await session.commit()

        assert await recover_stuck_jobs(session) == 1
        await session.refresh(job)
        assert job.status == "failed"
        assert job.last_error is not None and job.next_attempt_at is not None

        claimed = await claim_next_purge_job(session)
        assert claimed is not None and claimed.id == job.id
        assert claimed.status == "processing" and claimed.attempt_count == 1


@pytest.mark.asyncio
async def test_a_fresh_processing_job_is_never_claimed_twice(client) -> None:
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="single_claim")
        await _create_job(session, user, workspace.id)

        first = await claim_next_purge_job(session)
        assert first is not None and first.status == "processing"
        # The job is already owned: a second claim finds nothing to do.
        assert await claim_next_purge_job(session) is None
        assert await recover_stuck_jobs(session) == 0


@pytest.mark.asyncio
async def test_worker_cycle_processes_pending_jobs(client, monkeypatch) -> None:
    storage = FakeStorage()
    monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: storage)
    async with session_scope() as session:
        first_user, first_workspace = await _make_account(session, suffix="worker_one")
        second_user, second_workspace = await _make_account(session, suffix="worker_two")
        await _create_job(session, first_user, first_workspace.id)
        await _create_job(session, second_user, second_workspace.id)

        processed = await process_available_purge_jobs(session, limit=25)
        assert processed == 2
        assert await session.get(User, first_user.id) is None
        assert await session.get(User, second_user.id) is None
        # A second cycle has nothing left to claim: the run is idempotent.
        assert await process_available_purge_jobs(session, limit=25) == 0


@pytest.mark.asyncio
async def test_worker_entrypoint_runs_a_cycle_against_the_test_database(
    client, monkeypatch
) -> None:
    storage = FakeStorage()
    monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: storage)

    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="worker_entry")
        await _create_job(session, user, workspace.id)

    @asynccontextmanager
    async def _factory_session():
        async with session_scope() as session:
            yield session

    monkeypatch.setattr(
        "app.identity.purge_worker.get_session_factory", lambda: _factory_session
    )
    assert await run_once(batch=5) == 1
    async with session_scope() as session:
        assert await session.get(User, "usr_worker_entry") is None


@pytest.mark.asyncio
async def test_execute_purge_leaves_the_job_retryable_when_relational_delete_fails(
    client, monkeypatch
) -> None:
    monkeypatch.setattr("app.identity.purge.get_object_storage_provider", lambda: FakeStorage())

    async def _boom(db, job):
        raise RuntimeError("dsn=postgres://user:password@host/db")

    monkeypatch.setattr("app.identity.purge._purge_relational_data", _boom)
    async with session_scope() as session:
        user, workspace = await _make_account(session, suffix="sql_failure")
        user_id, workspace_id = user.id, workspace.id
        job = await _create_job(session, user, workspace_id)
        job_id = job.id
        claimed = await claim_next_purge_job(session)
        assert claimed is not None
        failed = await execute_purge(session, claimed)
        assert failed.status == "failed"
        assert "password" not in (failed.last_error or "")
        blocked = await session.get(User, user_id)
        assert blocked is not None and blocked.status == "deletion_pending"
        assert await session.get(Workspace, workspace_id) is not None
        assert job_id == failed.id
