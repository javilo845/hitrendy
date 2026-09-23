"""WAVE-013 — flujo de video sobre PostgreSQL y el proveedor demo offline."""

from __future__ import annotations

import asyncio
import copy
import io
import struct
from datetime import UTC, datetime, timedelta
from importlib import resources

import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import delete, select, update

from app.assets.models import Asset
from app.conversations.models import AIUsageEvent
from app.core.capabilities import Capability, get_runtime_capability_registry
from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_session_factory
from app.identity.models import AccountPurgeJob, WorkspaceMember
from app.identity.purge import run_account_purge
from app.projects.models import Project
from app.providers.storage import get_object_storage_provider
from app.providers.video import (
    DemoVideoGenerationProvider,
    VideoArtifact,
    VideoGenerationRequest,
    VideoJobState,
    VideoSubmission,
)
from app.videos import signing
from app.videos import worker as video_worker
from app.videos.models import VideoGenerationBudget, VideoGenerationJob

API = "/api/v1/videos"
STORYBOARD = {
    "hook": "Una propuesta vertical",
    "duration_seconds": 5,
    "aspect_ratio": "9:16",
    "voiceover": "Una idea breve para tu audiencia.",
    "music_direction": "Ritmo cálido.",
    "shots": [
        {
            "order": 1,
            "duration_seconds": 2,
            "visual": "Producto en primer plano.",
            "camera": "Acercamiento estable.",
            "on_screen_text": "Conócenos",
            "voiceover": "Presentamos una opción.",
            "transition": "Corte limpio",
        },
        {
            "order": 2,
            "duration_seconds": 2,
            "visual": "Detalle del producto.",
            "camera": "Movimiento suave.",
            "on_screen_text": "Pensado para ti",
            "voiceover": "Una propuesta práctica.",
            "transition": "Disolvencia breve",
        },
        {
            "order": 3,
            "duration_seconds": 1,
            "visual": "Cierre de marca.",
            "camera": "Plano medio vertical.",
            "on_screen_text": "Escríbenos",
            "voiceover": "Da el siguiente paso.",
            "transition": "Cierre suave",
        },
    ],
}


STORYBOARD_10 = {
    **copy.deepcopy(STORYBOARD),
    "duration_seconds": 10,
    "shots": [
        {
            **copy.deepcopy(STORYBOARD["shots"][0]),
            "duration_seconds": 5,
        },
        {
            **copy.deepcopy(STORYBOARD["shots"][1]),
            "order": 2,
            "duration_seconds": 5,
        },
    ],
}


@pytest_asyncio.fixture(autouse=True)
async def video_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path, e2e_database: None) -> None:
    del e2e_database
    monkeypatch.setattr(settings, "video_generation_enabled", True)
    monkeypatch.setattr(settings, "video_provider", "demo")
    monkeypatch.setattr(settings, "video_generation_model", "")
    monkeypatch.setattr(settings, "video_generation_allowed_durations", [5, 10])
    monkeypatch.setattr(settings, "object_storage_provider", "local")
    monkeypatch.setattr(settings, "object_storage_local_dir", str(tmp_path / "storage"))
    get_runtime_capability_registry()._outcome_store.clear(Capability.VIDEO_GENERATION)
    async with get_session_factory()() as db:
        await db.execute(delete(VideoGenerationJob))
        await db.execute(delete(VideoGenerationBudget))
        await db.execute(
            delete(AIUsageEvent).where(
                AIUsageEvent.capability == Capability.VIDEO_GENERATION.value
            )
        )
        await db.commit()


def _storyboard_for_duration(duration_seconds: int) -> dict:
    if duration_seconds == 5:
        return copy.deepcopy(STORYBOARD)
    if duration_seconds == 10:
        return copy.deepcopy(STORYBOARD_10)
    raise AssertionError(f"No existe una fixture E2E para {duration_seconds}s")


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 120, 60)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _stored_source_asset(workspace_id: str, asset_id: str) -> str:
    content = _png()
    storage_path = f"workspaces/{workspace_id}/uploads/{asset_id}.png"
    await get_object_storage_provider().put(
        key=storage_path,
        content=content,
        content_type="image/png",
    )
    async with get_session_factory()() as db:
        db.add(
            Asset(
                id=asset_id,
                workspace_id=workspace_id,
                original_name=f"{asset_id}.png",
                storage_path=storage_path,
                mime_type="image/png",
                file_size_bytes=len(content),
                asset_type="image",
                width=8,
                height=8,
            )
        )
        await db.commit()
    return asset_id


async def _delete_asset(asset_id: str) -> None:
    async with get_session_factory()() as db:
        await db.execute(delete(Asset).where(Asset.id == asset_id))
        await db.commit()


def _video_fixture(duration_seconds: int = 5) -> bytes:
    filename = f"demo-9x16-{duration_seconds}s.mp4"
    return resources.files("app.videos.fixtures").joinpath(filename).read_bytes()


async def _confirmed_job(
    client: AsyncClient,
    workspace_id: str,
    *,
    key: str,
    duration_seconds: int = 5,
    source_asset_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    headers = {"X-Workspace-Id": workspace_id}
    storyboard = _storyboard_for_duration(duration_seconds)
    preflight = await client.post(
        f"{API}/preflight",
        headers=headers,
        json={
            "storyboard": storyboard,
            "prompt": "Genera un clip vertical E2E.",
            "negative_prompt": "Sin texto ilegible.",
            "duration_seconds": duration_seconds,
            "source_asset_id": source_asset_id,
            "project_id": project_id,
        },
    )
    assert preflight.status_code == 200, preflight.text
    approved = preflight.json()
    assert approved["allowed"] is True

    response = await client.post(
        f"{API}/jobs",
        headers={**headers, "Idempotency-Key": key},
        json={
            "storyboard": storyboard,
            "prompt": "Genera un clip vertical E2E.",
            "negative_prompt": "Sin texto ilegible.",
            "duration_seconds": duration_seconds,
            "source_asset_id": source_asset_id,
            "project_id": project_id,
            "confirmed": True,
            "approval_token": approved["approval_token"],
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


async def _worker_cycle() -> str | None:
    async with get_session_factory()() as db:
        job = await video_worker.claim_next_job(db)
        if job is None:
            return None
        job_id = job.id
        await video_worker.execute_job(db, job)
        return job_id


async def _reload_job(job_id: str) -> VideoGenerationJob:
    async with get_session_factory()() as db:
        job = await db.get(VideoGenerationJob, job_id)
        assert job is not None
        return job


async def _workspace_user_id(workspace_id: str) -> str:
    async with get_session_factory()() as db:
        user_id = await db.scalar(
            select(WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .limit(1)
        )
    assert user_id is not None
    return user_id


class _CountingProvider:
    name = "demo"

    def __init__(
        self,
        *,
        pending_checks: int = 0,
        artifact: VideoArtifact | None = None,
        submit_error: BaseException | None = None,
        submit_delay: float = 0,
        download_error: BaseException | None = None,
        block_check: bool = False,
    ) -> None:
        self.inner = DemoVideoGenerationProvider()
        self.pending_checks = pending_checks
        self.artifact = artifact
        self.submit_error = submit_error
        self.submit_delay = submit_delay
        self.download_error = download_error
        self.submit_calls = 0
        self.check_calls = 0
        self.download_calls = 0
        self.check_entered = asyncio.Event()
        self.release_check = asyncio.Event()
        if not block_check:
            self.release_check.set()

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission:
        self.submit_calls += 1
        if self.submit_delay:
            await asyncio.sleep(self.submit_delay)
        if self.submit_error is not None:
            raise self.submit_error
        return await self.inner.submit(request)

    async def check(self, provider_job_id: str) -> VideoJobState:
        self.check_calls += 1
        self.check_entered.set()
        await self.release_check.wait()
        if self.check_calls <= self.pending_checks:
            return VideoJobState(
                provider_status="pending",
                ready=False,
                failed=False,
                error_code=None,
                error_message=None,
                cost_units=None,
            )
        return VideoJobState(
            provider_status="ready",
            ready=True,
            failed=False,
            error_code=None,
            error_message=None,
            cost_units=1,
        )

    async def download(self, provider_job_id: str, *, duration_seconds: int) -> VideoArtifact:
        self.download_calls += 1
        if self.download_error is not None:
            raise self.download_error
        if self.artifact is not None:
            return self.artifact
        return await self.inner.download(
            provider_job_id,
            duration_seconds=duration_seconds,
        )

    async def cancel(self, provider_job_id: str) -> bool:
        _ = provider_job_id
        return False


class _FailingStorage:
    async def put(self, *, key: str, content: bytes, content_type: str) -> None:
        del key, content, content_type
        raise RuntimeError("storage failure in test")

    async def delete(self, *, key: str) -> None:
        del key

    async def read(self, *, key: str) -> bytes:
        del key
        raise RuntimeError("storage failure in test")

    async def exists(self, *, key: str) -> bool:
        del key
        return False


class _TrackingStorage:
    def __init__(self, inner) -> None:
        self.inner = inner
        self.put_keys: list[str] = []

    async def put(self, *, key: str, content: bytes, content_type: str) -> None:
        self.put_keys.append(key)
        await self.inner.put(key=key, content=content, content_type=content_type)

    async def delete(self, *, key: str) -> None:
        await self.inner.delete(key=key)

    async def read(self, *, key: str) -> bytes:
        return await self.inner.read(key=key)

    async def exists(self, *, key: str) -> bool:
        return await self.inner.exists(key=key)


@pytest.mark.asyncio
async def test_demo_video_completes_through_postgres_and_private_storage(
    authenticated_client,
) -> None:
    client, workspace_id = authenticated_client
    created = await _confirmed_job(client, workspace_id, key="video-e2e-complete")

    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]

    response = await client.get(
        f"{API}/jobs/{created['id']}",
        headers={"X-Workspace-Id": workspace_id},
    )
    assert response.status_code == 200
    public = response.json()
    assert public["status"] == "succeeded"
    assert public["video_url"]
    assert "provider_job_id" not in public

    served = await client.get(public["video_url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("video/")
    assert served.headers["cache-control"] == "private, no-store"
    assert served.headers["accept-ranges"] == "none"
    assert served.content[4:8] == b"ftyp"

    async with get_session_factory()() as db:
        job = await db.get(VideoGenerationJob, created["id"])
        asset = await db.get(Asset, job.asset_id)
    assert job is not None
    assert asset is not None
    assert asset.asset_type == "video"
    assert asset.duration_seconds == 5
    assert await _worker_cycle() is None


class _BlockingDemoProvider:
    name = "demo"

    def __init__(self) -> None:
        self.inner = DemoVideoGenerationProvider()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.submit_calls = 0

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission:
        self.submit_calls += 1
        self.entered.set()
        await self.release.wait()
        return await self.inner.submit(request)

    async def check(self, provider_job_id: str) -> VideoJobState:
        return await self.inner.check(provider_job_id)

    async def download(self, provider_job_id: str, *, duration_seconds: int):
        return await self.inner.download(
            provider_job_id,
            duration_seconds=duration_seconds,
        )

    async def cancel(self, provider_job_id: str) -> bool:
        return await self.inner.cancel(provider_job_id)


@pytest.mark.asyncio
async def test_postgres_skip_locked_never_submits_one_video_twice(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _BlockingDemoProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)

    created = await _confirmed_job(client, workspace_id, key="video-e2e-lock")
    first = asyncio.create_task(_worker_cycle())
    await asyncio.wait_for(provider.entered.wait(), timeout=5)

    # The first worker still owns the row while the provider call is in flight.
    assert await asyncio.wait_for(_worker_cycle(), timeout=5) is None
    assert provider.submit_calls == 1

    provider.release.set()
    assert await asyncio.wait_for(first, timeout=10) == created["id"]

    # The second lifecycle pass polls and downloads; it never submits again.
    assert await _worker_cycle() == created["id"]
    assert provider.submit_calls == 1

    async with get_session_factory()() as db:
        job = await db.get(VideoGenerationJob, created["id"])
    assert job is not None
    assert job.status == "succeeded"


@pytest.mark.asyncio
async def test_storyboard_and_preflight_do_not_spend_or_call_provider(
    business_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = business_context["client"]
    workspace_id = business_context["workspace_id"]

    storyboard = await client.post(
        f"{API}/storyboard",
        headers={"X-Workspace-Id": workspace_id},
        json={"business_id": business_context["business"]["id"]},
    )
    assert storyboard.status_code == 200, storyboard.text
    assert storyboard.json()["budget"]["remaining"] == 2

    def provider_must_not_be_called():
        raise AssertionError("storyboard/preflight no debe resolver el proveedor")

    monkeypatch.setattr(video_worker, "get_video_generation_provider", provider_must_not_be_called)
    preflight = await client.post(
        f"{API}/preflight",
        headers={"X-Workspace-Id": workspace_id},
        json={
            "storyboard": STORYBOARD,
            "prompt": "Preflight sin submit.",
            "negative_prompt": None,
            "duration_seconds": 5,
            "source_asset_id": None,
            "project_id": None,
        },
    )
    assert preflight.status_code == 200
    assert preflight.json()["allowed"] is True
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 0


@pytest.mark.asyncio
async def test_e2e_idempotency_rejects_a_different_payload_without_second_reservation(
    authenticated_client,
) -> None:
    client, workspace_id = authenticated_client
    created = await _confirmed_job(client, workspace_id, key="video-e2e-idempotency")
    headers = {"X-Workspace-Id": workspace_id}

    changed_storyboard = _storyboard_for_duration(5)
    approved = await client.post(
        f"{API}/preflight",
        headers=headers,
        json={
            "storyboard": changed_storyboard,
            "prompt": "Otro payload para la misma key.",
            "negative_prompt": None,
            "duration_seconds": 5,
            "source_asset_id": None,
            "project_id": None,
        },
    )
    assert approved.status_code == 200
    assert approved.json()["allowed"] is True
    conflict = await client.post(
        f"{API}/jobs",
        headers={**headers, "Idempotency-Key": "video-e2e-idempotency"},
        json={
            "storyboard": changed_storyboard,
            "prompt": "Otro payload para la misma key.",
            "negative_prompt": None,
            "duration_seconds": 5,
            "source_asset_id": None,
            "project_id": None,
            "confirmed": True,
            "approval_token": approved.json()["approval_token"],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 1
    assert created["status"] == "queued"


@pytest.mark.asyncio
async def test_concurrent_budget_reservation_allows_only_one_job(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    monkeypatch.setattr(settings, "video_generation_daily_budget", 1)
    headers = {"X-Workspace-Id": workspace_id}

    async def approved(key: str) -> tuple[str, dict]:
        response = await client.post(
            f"{API}/preflight",
            headers=headers,
            json={
                "storyboard": STORYBOARD,
                "prompt": f"Reserva {key}.",
                "negative_prompt": None,
                "duration_seconds": 5,
                "source_asset_id": None,
                "project_id": None,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["allowed"] is True
        return key, {
            "storyboard": STORYBOARD,
            "prompt": f"Reserva {key}.",
            "negative_prompt": None,
            "duration_seconds": 5,
            "source_asset_id": None,
            "project_id": None,
            "confirmed": True,
            "approval_token": body["approval_token"],
        }

    first_key, first_payload = await approved("budget-a")
    second_key, second_payload = await approved("budget-b")
    responses = await asyncio.gather(
        client.post(f"{API}/jobs", headers={**headers, "Idempotency-Key": first_key}, json=first_payload),
        client.post(
            f"{API}/jobs",
            headers={**headers, "Idempotency-Key": second_key},
            json=second_payload,
        ),
    )
    assert sorted(response.status_code for response in responses) == [202, 429]


@pytest.mark.asyncio
async def test_postgres_pending_job_polls_five_times_without_resubmitting(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(pending_checks=5)
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-five-polls")

    assert await _worker_cycle() == created["id"]
    for _ in range(5):
        assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]

    job = await _reload_job(created["id"])
    assert provider.submit_calls == 1
    assert provider.check_calls >= 5
    assert job.status == "succeeded"
    assert job.attempt_count == 1
    assert job.poll_count == 6


@pytest.mark.asyncio
async def test_postgres_active_poll_lease_blocks_second_worker(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(pending_checks=1, block_check=True)
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-poll-lease")
    assert await _worker_cycle() == created["id"]

    first = asyncio.create_task(_worker_cycle())
    await asyncio.wait_for(provider.check_entered.wait(), timeout=5)
    assert await asyncio.wait_for(_worker_cycle(), timeout=5) is None
    assert provider.check_calls == 1

    provider.release_check.set()
    assert await asyncio.wait_for(first, timeout=10) == created["id"]
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "succeeded"
    assert provider.submit_calls == 1


@pytest.mark.asyncio
async def test_postgres_expired_poll_lease_is_recoverable(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-expired-poll")
    assert await _worker_cycle() == created["id"]
    stale = datetime.now(UTC) - timedelta(
        seconds=settings.video_generation_stuck_after_seconds + 1
    )
    async with get_session_factory()() as db:
        await db.execute(
            update(VideoGenerationJob)
            .where(VideoGenerationJob.id == created["id"])
            .values(claim_token="dead-poll-lease", claimed_at=stale, last_polled_at=stale)
        )
        await db.commit()

    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "succeeded"
    assert provider.submit_calls == 1
    assert provider.check_calls == 1


@pytest.mark.asyncio
async def test_flag_disabled_before_submit_refunds_without_provider_call(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-disabled-submit")
    monkeypatch.setattr(settings, "video_generation_enabled", False)

    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "capability_unavailable"
    assert provider.submit_calls == 0
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 0


@pytest.mark.asyncio
async def test_disabling_flag_after_submit_continues_persisted_provider_job(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(pending_checks=1)
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-disabled-poll")
    assert await _worker_cycle() == created["id"]
    monkeypatch.setattr(settings, "video_generation_enabled", False)
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "succeeded"
    assert provider.submit_calls == 1
    assert provider.check_calls == 2


@pytest.mark.asyncio
async def test_provider_route_change_before_submit_refunds_without_submit(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-route-change")
    monkeypatch.setattr(settings, "video_provider", "other-provider")

    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "provider_route_unavailable"
    assert provider.submit_calls == 0
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 0


@pytest.mark.asyncio
async def test_source_asset_deleted_before_submit_fails_and_refunds(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    source_id = await _stored_source_asset(workspace_id, "source-before-submit")
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    created = await _confirmed_job(
        client,
        workspace_id,
        key="video-e2e-source-before",
        source_asset_id=source_id,
    )
    await _delete_asset(source_id)

    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "source_asset_missing"
    assert provider.submit_calls == 0
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 0


@pytest.mark.asyncio
async def test_source_asset_deleted_after_submit_does_not_resubmit(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    source_id = await _stored_source_asset(workspace_id, "source-after-submit")
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    created = await _confirmed_job(
        client,
        workspace_id,
        key="video-e2e-source-after",
        source_asset_id=source_id,
    )
    assert await _worker_cycle() == created["id"]
    await _delete_asset(source_id)
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "succeeded"
    assert job.source_asset_id == source_id
    assert provider.submit_calls == 1


@pytest.mark.asyncio
async def test_submit_timeout_is_execution_unknown_and_not_refunded(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(submit_delay=1)
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_timeout_seconds", 0.01)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-submit-timeout")

    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "execution_unknown"
    assert job.last_error_code == "execution_unknown"
    assert provider.submit_calls == 1
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 1


@pytest.mark.asyncio
async def test_provider_rejection_after_submit_is_terminal_and_not_refunded(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(
        submit_error=AppError(
            "provider_invalid_request",
            "provider rejected request",
            status_code=422,
        )
    )
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-provider-rejected")

    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "provider_rejected"
    assert provider.submit_calls == 1

    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
        usage = list(
            await db.scalars(
                select(AIUsageEvent).where(
                    AIUsageEvent.workspace_id == workspace_id,
                    AIUsageEvent.capability == Capability.VIDEO_GENERATION.value,
                )
            )
        )
    assert budget is not None and budget.consumed == 1
    assert len(usage) == 1
    assert usage[0].reported_cost is None
    assert await _worker_cycle() is None
    assert provider.submit_calls == 1


@pytest.mark.asyncio
async def test_dead_worker_during_submitting_is_fenced_as_execution_unknown(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-dead-submit")
    stale = datetime.now(UTC) - timedelta(
        seconds=settings.video_generation_stuck_after_seconds + 1
    )
    async with get_session_factory()() as db:
        await db.execute(
            update(VideoGenerationJob)
            .where(VideoGenerationJob.id == created["id"])
            .values(
                status="submitting",
                claim_token="dead-submit-lease",
                claimed_at=stale,
                submitted_at=stale,
            )
        )
        await db.commit()

    assert await _worker_cycle() is None
    job = await _reload_job(created["id"])
    assert job.status == "execution_unknown"
    assert job.last_error_code == "execution_unknown"
    assert provider.submit_calls == 0
    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
    assert budget is not None and budget.consumed == 1


@pytest.mark.asyncio
async def test_provider_job_survives_worker_restart_without_second_submit(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    first_provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: first_provider)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-restart")
    assert await _worker_cycle() == created["id"]

    restarted_provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: restarted_provider)
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "succeeded"
    assert first_provider.submit_calls == 1
    assert restarted_provider.submit_calls == 0
    assert restarted_provider.check_calls == 1


@pytest.mark.asyncio
async def test_download_failure_is_terminal_after_provider_boundary(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(download_error=RuntimeError("download failed"))
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-download-failure")
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "download_failed"
    assert provider.submit_calls == 1


@pytest.mark.asyncio
async def test_storage_failure_is_terminal_after_valid_download(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(video_worker, "get_object_storage_provider", _FailingStorage)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-storage-failure")
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "storage_failed"
    assert provider.submit_calls == 1


@pytest.mark.asyncio
async def test_post_storage_failure_rolls_back_asset_and_closes_job(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    real_storage = get_object_storage_provider()
    tracking_storage = _TrackingStorage(real_storage)
    monkeypatch.setattr(video_worker, "get_object_storage_provider", lambda: tracking_storage)

    original_record_usage = video_worker._record_usage
    failures = 0

    async def fail_once(*args, **kwargs):
        nonlocal failures
        if failures == 0:
            failures += 1
            raise RuntimeError("failure after storage.put")
        return await original_record_usage(*args, **kwargs)

    monkeypatch.setattr(video_worker, "_record_usage", fail_once)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-post-storage-failure")
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]

    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "storage_failed"
    assert job.asset_id is None
    assert provider.download_calls == 1

    async with get_session_factory()() as db:
        budget = await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        )
        assert budget is not None and budget.consumed == 1
        assert (
            await db.scalar(
                select(Asset.id).where(
                    Asset.workspace_id == workspace_id,
                    Asset.asset_type == "video",
                )
            )
            is None
        )

    assert tracking_storage.put_keys
    for key in tracking_storage.put_keys:
        assert await real_storage.exists(key=key) is False
    assert await _worker_cycle() is None


@pytest.mark.asyncio
async def test_invalid_mp4_is_rejected_after_provider_download(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(
        artifact=VideoArtifact(content=_video_fixture()[:64], mime_type="video/mp4")
    )
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    created = await _confirmed_job(client, workspace_id, key="video-e2e-invalid-mp4")
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.status == "failed"
    assert job.last_error_code == "invalid_container"


@pytest.mark.asyncio
async def test_wrong_duration_and_ratio_are_rejected(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    provider = _CountingProvider(
        artifact=VideoArtifact(content=_video_fixture(5), mime_type="video/mp4")
    )
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)
    wrong_duration = await _confirmed_job(
        client,
        workspace_id,
        key="video-e2e-wrong-duration",
        duration_seconds=10,
    )
    assert await _worker_cycle() == wrong_duration["id"]
    assert await _worker_cycle() == wrong_duration["id"]
    duration_job = await _reload_job(wrong_duration["id"])
    assert duration_job.status == "failed"
    assert duration_job.last_error_code == "invalid_duration"

    content = bytearray(_video_fixture())
    marker = content.find(b"tkhd")
    assert marker >= 4
    box_start = marker - 4
    box_size = struct.unpack_from(">I", content, box_start)[0]
    struct.pack_into(">II", content, box_start + box_size - 8, 640 << 16, 360 << 16)
    ratio_provider = _CountingProvider(
        artifact=VideoArtifact(content=bytes(content), mime_type="video/mp4")
    )
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: ratio_provider)
    wrong_ratio = await _confirmed_job(client, workspace_id, key="video-e2e-wrong-ratio")
    assert await _worker_cycle() == wrong_ratio["id"]
    assert await _worker_cycle() == wrong_ratio["id"]
    ratio_job = await _reload_job(wrong_ratio["id"])
    assert ratio_job.status == "failed"
    assert ratio_job.last_error_code == "invalid_ratio"


@pytest.mark.asyncio
async def test_video_url_valid_expired_and_forged(
    authenticated_client,
) -> None:
    client, workspace_id = authenticated_client
    created = await _confirmed_job(client, workspace_id, key="video-e2e-url")
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]
    response = await client.get(
        f"{API}/jobs/{created['id']}",
        headers={"X-Workspace-Id": workspace_id},
    )
    public = response.json()
    assert response.status_code == 200
    assert (await client.get(public["video_url"])).status_code == 200

    job = await _reload_job(created["id"])
    expired_at = datetime.now(UTC) - timedelta(minutes=1)
    expired_signature = signing.sign_video_url(job.asset_id, workspace_id, expired_at)
    expired_url = (
        f"{API}/files/{job.asset_id}?workspace={workspace_id}"
        f"&expires={int(expired_at.timestamp())}&signature={expired_signature}"
    )
    assert (await client.get(expired_url)).status_code == 404
    forged = public["video_url"][:-1] + ("0" if public["video_url"][-1] != "0" else "1")
    assert (await client.get(forged)).status_code == 404


@pytest.mark.asyncio
async def test_workspace_project_and_source_asset_isolation_and_latest_job(
    client_factory,
) -> None:
    client_a, workspace_a = await client_factory(workspace_name="Workspace A")
    client_b, workspace_b = await client_factory(workspace_name="Workspace B")
    project_id = "project-video-isolation"
    async with get_session_factory()() as db:
        db.add(
            Project(
                id=project_id,
                workspace_id=workspace_a,
                business_id="business-video-isolation",
                name="Proyecto A",
                platform="instagram",
            )
        )
        await db.commit()
    source_id = await _stored_source_asset(workspace_a, "source-workspace-a")
    created = await _confirmed_job(
        client_a,
        workspace_a,
        key="video-e2e-latest",
        project_id=project_id,
    )

    latest = await client_a.get(
        f"{API}/jobs",
        params={"project_id": project_id, "latest": "true"},
        headers={"X-Workspace-Id": workspace_a},
    )
    assert latest.status_code == 200
    assert latest.json()["job"]["id"] == created["id"]

    foreign_job = await client_b.get(
        f"{API}/jobs/{created['id']}",
        headers={"X-Workspace-Id": workspace_a},
    )
    assert foreign_job.status_code == 403
    foreign_project = await client_b.post(
        f"{API}/preflight",
        headers={"X-Workspace-Id": workspace_b},
        json={
            "storyboard": STORYBOARD,
            "prompt": "Proyecto ajeno.",
            "negative_prompt": None,
            "duration_seconds": 5,
            "source_asset_id": None,
            "project_id": project_id,
        },
    )
    assert foreign_project.status_code == 404
    foreign_source = await client_b.post(
        f"{API}/preflight",
        headers={"X-Workspace-Id": workspace_b},
        json={
            "storyboard": STORYBOARD,
            "prompt": "Fuente ajena.",
            "negative_prompt": None,
            "duration_seconds": 5,
            "source_asset_id": source_id,
            "project_id": None,
        },
    )
    assert foreign_source.status_code == 404


@pytest.mark.asyncio
async def test_run_once_records_real_actor_from_durable_job(
    authenticated_client,
) -> None:
    client, workspace_id = authenticated_client
    created = await _confirmed_job(client, workspace_id, key="video-e2e-run-once")
    assert await video_worker.run_once(batch=2) == 2
    job = await _reload_job(created["id"])
    assert job.status == "succeeded"
    async with get_session_factory()() as db:
        event = await db.scalar(
            select(AIUsageEvent).where(
                AIUsageEvent.workspace_id == workspace_id,
                AIUsageEvent.capability == Capability.VIDEO_GENERATION.value,
            )
        )
    assert event is not None
    assert event.user_id == await _workspace_user_id(workspace_id)


@pytest.mark.asyncio
async def test_refund_targets_original_ledger_after_day_changes(
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, workspace_id = authenticated_client
    created = await _confirmed_job(client, workspace_id, key="video-e2e-midnight-refund")
    async with get_session_factory()() as db:
        job = await db.get(VideoGenerationJob, created["id"])
        assert job is not None
        budget_id = job.budget_id
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        await db.execute(
            update(VideoGenerationBudget)
            .where(VideoGenerationBudget.id == budget_id)
            .values(day=yesterday)
        )
        await db.commit()
    monkeypatch.setattr(settings, "video_generation_enabled", False)
    assert await _worker_cycle() == created["id"]
    async with get_session_factory()() as db:
        budget = await db.get(VideoGenerationBudget, budget_id)
    assert budget is not None
    assert budget.consumed == 0
    assert budget.day == yesterday


@pytest.mark.asyncio
async def test_video_purge_removes_job_budget_asset_and_private_bytes(
    authenticated_client,
) -> None:
    client, workspace_id = authenticated_client
    created = await _confirmed_job(client, workspace_id, key="video-e2e-purge")
    assert await _worker_cycle() == created["id"]
    assert await _worker_cycle() == created["id"]
    job = await _reload_job(created["id"])
    assert job.asset_id is not None
    async with get_session_factory()() as db:
        asset = await db.get(Asset, job.asset_id)
        assert asset is not None
        object_key = asset.storage_path
        user_id = await db.scalar(
            select(WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .limit(1)
        )
        assert user_id is not None
        purge = AccountPurgeJob(
            id="purge-video-e2e",
            user_id=user_id,
            workspace_id=workspace_id,
        )
        db.add(purge)
        await db.commit()
        result = await run_account_purge(db, purge)
        assert result.status == "completed"
    assert await get_object_storage_provider().exists(key=object_key) is False
    async with get_session_factory()() as db:
        assert await db.get(VideoGenerationJob, created["id"]) is None
        assert await db.get(Asset, job.asset_id) is None
        assert await db.scalar(
            select(VideoGenerationBudget).where(
                VideoGenerationBudget.workspace_id == workspace_id
            )
        ) is None


@pytest.mark.asyncio
async def test_video_has_no_publication_endpoint(authenticated_client) -> None:
    client, workspace_id = authenticated_client
    response = await client.post(
        f"{API}/publish",
        headers={"X-Workspace-Id": workspace_id},
        json={"job_id": "does-not-exist"},
    )
    assert response.status_code == 404
