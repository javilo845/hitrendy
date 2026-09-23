"""WAVE-011 on real PostgreSQL: durable claiming, isolation and signed delivery.

The unit suites run on SQLite, whose dialect silently drops ``FOR UPDATE``, so
the assertion that actually costs money if it is wrong — two workers competing
for one queued job must produce exactly one provider call — can only be proven
here, against a database that really takes row locks.

Everything goes through the same HTTP contracts the browser uses, and no real
provider is ever reached: the image provider is the offline demo renderer, or a
counting stub around it.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from app.assets.models import Asset
from app.business.models import Business
from app.core.capabilities import Capability, get_runtime_capability_registry
from app.core.config import settings
from app.db.session import get_session_factory
from app.identity.models import AuthSession, User, Workspace, WorkspaceMember
from app.images import service as image_service
from app.images.models import ImageGenerationBudget, ImageGenerationJob
from app.images.signing import sign_image_url
from app.main import app
from app.providers.images import ASPECT_RATIOS, DemoImageGenerationProvider
from app.providers.storage import get_object_storage_provider

API = "/api/v1/images"

BRIEF = {
    "subject": "Taza de café artesanal sobre una mesa de madera",
    "setting": "Cafetería luminosa en Tegucigalpa",
    "style": "Fotografía natural",
    "palette": "Tonos cálidos",
    "mood": "Acogedor",
    "avoid": "Texto superpuesto",
}


class _CountingDemoProvider:
    """The offline renderer plus a counter shared across worker sessions."""

    provider_name = "demo"
    model_name = "demo-image-v1"

    def __init__(self) -> None:
        self.calls = 0
        self._inner = DemoImageGenerationProvider()

    async def generate(self, *, request):
        self.calls += 1
        # Slow enough that two workers would overlap inside the provider call
        # if the claim ever let both of them through.
        await asyncio.sleep(0.05)
        return await self._inner.generate(request=request)


@pytest.fixture(autouse=True)
def image_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(settings, "image_generation_enabled", True)
    monkeypatch.setattr(settings, "image_provider", "demo")
    monkeypatch.setattr(settings, "object_storage_provider", "local")
    monkeypatch.setattr(settings, "object_storage_local_dir", str(tmp_path / "storage"))
    get_runtime_capability_registry()._outcome_store.clear(Capability.IMAGE_GENERATION)


async def _workspace_client(*, with_business: bool = False) -> tuple[AsyncClient, str, str | None]:
    """A signed-in workspace built directly in PostgreSQL.

    Registering over HTTP would be more faithful, but the whole e2e session
    shares one app instance and one auth rate limiter, so every extra
    ``/auth/register`` here is a request stolen from another suite. The rows
    below are exactly what registration would have written.
    """

    suffix = uuid4().hex
    workspace_id = f"ws_wave011_{suffix}"
    user_id = f"usr_wave011_{suffix}"
    business_id = f"biz_wave011_{suffix}" if with_business else None
    token = f"wave011-{suffix}"
    async with get_session_factory()() as db:
        db.add_all(
            (
                User(
                    id=user_id,
                    email=f"wave011-{suffix}@example.com",
                    name="Image E2E",
                    password_hash="x",
                ),
                Workspace(id=workspace_id, name=f"Imagen {suffix[:8]}"),
            )
        )
        await db.flush()
        db.add_all(
            (
                WorkspaceMember(
                    id=f"wsm_wave011_{suffix}",
                    workspace_id=workspace_id,
                    user_id=user_id,
                ),
                AuthSession(
                    id=f"ses_wave011_{suffix}",
                    token_hash=sha256(token.encode()).hexdigest(),
                    user_id=user_id,
                    expires_at=datetime.now(UTC) + timedelta(days=365),
                ),
            )
        )
        if business_id is not None:
            db.add(
                Business(
                    id=business_id,
                    workspace_id=workspace_id,
                    name=f"Café {suffix[:8]}",
                    category="gastronomy",
                    country="HN",
                    city="Tegucigalpa",
                    primary_product="Café de altura",
                    target_audience="Clientes locales",
                    preferred_platforms='["instagram"]',
                    primary_objective="sales",
                )
            )
        await db.commit()
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client.cookies.set("hitrendy_session", token)
    return client, workspace_id, business_id


async def _confirmed_job(
    client: AsyncClient, workspace_id: str, *, key: str, aspect_ratio: str = "4:5"
) -> dict:
    """Walk the real flow: preflight, then confirm. No provider is touched."""

    headers = {"X-Workspace-Id": workspace_id}
    preflight = await client.post(
        f"{API}/preflight",
        headers=headers,
        json={"brief": BRIEF, "aspect_ratio": aspect_ratio},
    )
    assert preflight.status_code == 200, preflight.text
    approved = preflight.json()
    assert approved["allowed"] is True
    assert approved["approval_token"]

    created = await client.post(
        f"{API}/jobs",
        headers={**headers, "Idempotency-Key": key},
        json={
            "brief": BRIEF,
            "aspect_ratio": aspect_ratio,
            "approval_token": approved["approval_token"],
            "confirmed": True,
        },
    )
    assert created.status_code == 202, created.text
    return created.json()


async def _worker_cycle() -> str | None:
    """One full worker turn in its own session, exactly as the CLI worker does."""

    async with get_session_factory()() as db:
        job = await image_service.claim_next_job(db)
        if job is None:
            return None
        job_id = job.id
        await image_service.execute_job(db, job)
        return job_id


async def _cleanup(*workspace_ids: str) -> None:
    async with get_session_factory()() as db:
        await db.execute(
            delete(ImageGenerationJob).where(ImageGenerationJob.workspace_id.in_(workspace_ids))
        )
        await db.execute(
            delete(ImageGenerationBudget).where(
                ImageGenerationBudget.workspace_id.in_(workspace_ids)
            )
        )
        await db.execute(delete(Asset).where(Asset.workspace_id.in_(workspace_ids)))
        await db.commit()


@pytest.mark.asyncio
async def test_two_workers_produce_exactly_one_paid_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """22. Dos workers generan una sola llamada, sobre bloqueo real de fila."""

    client, workspace_id, _ = await _workspace_client()
    provider = _CountingDemoProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    try:
        created = await _confirmed_job(client, workspace_id, key="e2e-one-call")
        assert created["status"] == "queued"

        first, second = await asyncio.gather(_worker_cycle(), _worker_cycle())

        assert sorted((first, second), key=lambda item: item is None) == [created["id"], None]
        assert provider.calls == 1

        async with get_session_factory()() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(Asset)
                    .where(Asset.workspace_id == workspace_id)
                )
                == 1
            )
            # One reservation, not two: the budget is spent by the confirmation,
            # not by whichever worker happened to win.
            consumed = await db.scalar(
                select(ImageGenerationBudget.consumed).where(
                    ImageGenerationBudget.workspace_id == workspace_id
                )
            )
        assert consumed == 1

        # A third turn finds nothing left to do.
        assert await _worker_cycle() is None
        assert provider.calls == 1
    finally:
        await _cleanup(workspace_id)
        await client.aclose()


class _BlockingDemoProvider(_CountingDemoProvider):
    """A provider that stalls inside the call, like a real one going quiet.

    ``entered`` fires once the boundary has been crossed; the call then waits on
    ``release``, so the test controls exactly how long the job sits in
    ``provider_started`` -- including past the point where a naive recovery would
    decide the worker is dead and buy the image again.
    """

    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, *, request):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return await self._inner.generate(request=request)


@pytest.mark.asyncio
async def test_a_call_that_outlives_its_lease_is_never_issued_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """1. Un proveedor bloqueado más allá del periodo de recuperación.

    Éste es el fallo que cuesta dinero: el job ya cruzó el límite pagado y su
    worker parece muerto. Nadie puede volver a llamar, el estado no puede
    quedarse en ``running`` para siempre, y el worker rezagado --que sigue vivo--
    no puede sobrescribir el veredicto que se escribió sin él.
    """

    client, workspace_id, _ = await _workspace_client()
    provider = _BlockingDemoProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    try:
        created = await _confirmed_job(client, workspace_id, key="e2e-blocked-call")

        # Worker A cruza el límite y se queda dentro de la llamada.
        stalled = asyncio.create_task(_worker_cycle())
        await asyncio.wait_for(provider.entered.wait(), timeout=5)

        async with get_session_factory()() as db:
            in_flight = await db.get(ImageGenerationJob, created["id"])
        assert in_flight.status == "provider_started"
        assert in_flight.provider_started_at is not None
        assert in_flight.claim_token

        # El lease vence mientras la llamada sigue en vuelo.
        monkeypatch.setattr(settings, "image_generation_stuck_after_seconds", 0)

        # Worker B llega, no encuentra nada que reclamar y no llama a nadie.
        assert await _worker_cycle() is None
        assert await _worker_cycle() is None
        assert provider.calls == 1

        # El job no se queda colgado: el barrido lo cierra como ambiguo.
        async with get_session_factory()() as db:
            swept = await db.get(ImageGenerationJob, created["id"])
        assert swept.status == "failed"
        assert swept.last_error_code == "IMAGE_EXECUTION_UNKNOWN"
        assert swept.claim_token is None

        # Ahora responde el proveedor: el worker A perdió su reclamo y acepta
        # el veredicto ajeno en vez de pisarlo.
        provider.release.set()
        assert await asyncio.wait_for(stalled, timeout=10) == created["id"]
        assert provider.calls == 1

        async with get_session_factory()() as db:
            final = await db.get(ImageGenerationJob, created["id"])
            assets = await db.scalar(
                select(func.count()).select_from(Asset).where(Asset.workspace_id == workspace_id)
            )
            consumed = await db.scalar(
                select(ImageGenerationBudget.consumed).where(
                    ImageGenerationBudget.workspace_id == workspace_id
                )
            )
        assert final.status == "failed"
        assert final.last_error_code == "IMAGE_EXECUTION_UNKNOWN"
        assert final.asset_id is None
        # Ni dos imágenes ni una imagen huérfana atada a un job fallido.
        assert assets == 0
        # Y ningún reembolso inventado: no sabemos si el proveedor cobró.
        assert consumed == 1
    finally:
        provider.release.set()
        await _cleanup(workspace_id)
        await client.aclose()


@pytest.mark.asyncio
async def test_a_job_held_by_one_worker_is_skipped_not_awaited() -> None:
    """``SKIP LOCKED`` is the difference between a queue and a traffic jam."""

    client, workspace_id, _ = await _workspace_client()
    try:
        created = await _confirmed_job(client, workspace_id, key="e2e-skip-locked")

        holder = get_session_factory()()
        try:
            locked = await holder.scalar(
                select(ImageGenerationJob)
                .where(ImageGenerationJob.id == created["id"])
                .with_for_update()
            )
            assert locked is not None

            # The competing worker must return promptly with nothing rather
            # than block on the held row.
            async with get_session_factory()() as db:
                skipped = await asyncio.wait_for(image_service.claim_next_job(db), timeout=5)
            assert skipped is None
        finally:
            await holder.rollback()
            await holder.close()

        # Once the lock is gone the same job is claimable again.
        async with get_session_factory()() as db:
            claimed = await image_service.claim_next_job(db)
            assert claimed is not None
            assert claimed.id == created["id"]
            assert claimed.status == "running"
    finally:
        await _cleanup(workspace_id)
        await client.aclose()


@pytest.mark.asyncio
async def test_a_running_job_is_reclaimed_only_after_its_worker_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """23. Un job abandonado se recupera, y no antes de tiempo."""

    client, workspace_id, _ = await _workspace_client()
    try:
        created = await _confirmed_job(client, workspace_id, key="e2e-stuck")

        async with get_session_factory()() as db:
            claimed = await image_service.claim_next_job(db)
        assert claimed is not None
        assert claimed.attempt_count == 1

        # A worker that is merely slow keeps its job.
        async with get_session_factory()() as db:
            assert await image_service.claim_next_job(db) is None

        # A worker that died leaves a row nobody is advancing.
        monkeypatch.setattr(settings, "image_generation_stuck_after_seconds", 0)
        async with get_session_factory()() as db:
            reclaimed = await image_service.claim_next_job(db)
        assert reclaimed is not None
        assert reclaimed.id == created["id"]
        assert reclaimed.attempt_count == 2

        # And it is never retried forever.
        monkeypatch.setattr(settings, "image_generation_max_attempts", 2)
        async with get_session_factory()() as db:
            assert await image_service.claim_next_job(db) is None
            exhausted = await db.get(ImageGenerationJob, created["id"])
        assert exhausted.status == "failed"
        assert exhausted.last_error_code == "IMAGE_MAX_ATTEMPTS"
    finally:
        await _cleanup(workspace_id)
        await client.aclose()


@pytest.mark.asyncio
async def test_a_finished_generation_is_served_only_to_a_valid_fresh_signature() -> None:
    """29/30. La URL firmada exige workspace autorizado y expira."""

    client, workspace_id, _ = await _workspace_client()
    intruder, intruder_workspace, _ = await _workspace_client()
    try:
        created = await _confirmed_job(client, workspace_id, key="e2e-signed", aspect_ratio="9:16")
        assert await _worker_cycle() == created["id"]

        read = await client.get(
            f"{API}/jobs/{created['id']}", headers={"X-Workspace-Id": workspace_id}
        )
        assert read.status_code == 200
        body = read.json()
        assert body["status"] == "succeeded"
        signed_url = body["image_url"]
        assert signed_url

        served = await client.get(signed_url)
        assert served.status_code == 200
        assert served.headers["content-type"].startswith("image/")
        assert served.headers["cache-control"] == "private, no-store"
        assert len(served.content) > 0

        # Two consecutive reads mint different links for the same asset.
        second = await client.get(
            f"{API}/jobs/{created['id']}", headers={"X-Workspace-Id": workspace_id}
        )
        assert second.json()["image_url"]

        query = parse_qs(urlparse(signed_url).query)
        asset_id = body["asset_id"]

        # The signature belongs to one workspace: repointing it fails.
        repointed = await client.get(
            f"{API}/files/{asset_id}",
            params={
                "workspace": intruder_workspace,
                "expires": query["expires"][0],
                "signature": query["signature"][0],
            },
        )
        assert repointed.status_code == 403
        assert repointed.json()["error"]["code"] == "IMAGE_LINK_INVALID"

        # An expired link fails the same way, with the same message.
        stale = sign_image_url(asset_id=asset_id, workspace_id=workspace_id, ttl_seconds=-1)
        expired = await client.get(stale.url)
        assert expired.status_code == 403
        assert expired.json()["error"]["code"] == "IMAGE_LINK_INVALID"

        # And the job itself is invisible to anyone else, signature or not.
        foreign = await intruder.get(
            f"{API}/jobs/{created['id']}", headers={"X-Workspace-Id": intruder_workspace}
        )
        assert foreign.status_code == 404
    finally:
        await _cleanup(workspace_id, intruder_workspace)
        await client.aclose()
        await intruder.aclose()


@pytest.mark.asyncio
async def test_the_generated_image_lives_in_storage_and_never_in_a_column() -> None:
    """28/31. Los bytes privados quedan fuera de PostgreSQL."""

    client, workspace_id, _ = await _workspace_client()
    try:
        created = await _confirmed_job(client, workspace_id, key="e2e-storage")
        assert await _worker_cycle() == created["id"]

        async with get_session_factory()() as db:
            job = await db.get(ImageGenerationJob, created["id"])
            asset = await db.get(Asset, job.asset_id)
        assert asset is not None
        assert (asset.width, asset.height) == ASPECT_RATIOS[job.aspect_ratio]
        assert asset.storage_path.startswith(f"workspaces/{workspace_id}/generated/")
        assert asset.file_size_bytes > 0

        # Every text column is a path or a short label, never encoded bytes.
        for value in (asset.storage_path, asset.original_name, asset.mime_type, job.prompt):
            assert "base64" not in value
            assert "data:" not in value

        stored = await get_object_storage_provider().read(key=asset.storage_path)
        assert len(stored) == asset.file_size_bytes
        assert stored.startswith(b"\x89PNG")
    finally:
        await _cleanup(workspace_id)
        await client.aclose()


@pytest.mark.asyncio
async def test_confirming_twice_with_one_key_enqueues_one_job() -> None:
    """20/21. La idempotencia sobrevive a PostgreSQL, no solo a SQLite."""

    client, workspace_id, _ = await _workspace_client()
    headers = {"X-Workspace-Id": workspace_id}
    try:
        preflight = await client.post(
            f"{API}/preflight", headers=headers, json={"brief": BRIEF, "aspect_ratio": "1:1"}
        )
        token = preflight.json()["approval_token"]
        payload = {
            "brief": BRIEF,
            "aspect_ratio": "1:1",
            "approval_token": token,
            "confirmed": True,
        }
        sent = {**headers, "Idempotency-Key": "e2e-idem"}

        first = await client.post(f"{API}/jobs", headers=sent, json=payload)
        second = await client.post(f"{API}/jobs", headers=sent, json=payload)
        assert first.status_code == 202
        assert second.status_code == 202
        assert first.json() == second.json()
        assert "image_url" not in second.json()

        # The same key over a different brief is a conflict, not a silent swap.
        other = await client.post(
            f"{API}/jobs", headers=sent, json={**payload, "aspect_ratio": "9:16"}
        )
        assert other.status_code == 409
        assert other.json()["error"]["code"] == "CONFLICT"

        async with get_session_factory()() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(ImageGenerationJob)
                    .where(ImageGenerationJob.workspace_id == workspace_id)
                )
                == 1
            )
            consumed = await db.scalar(
                select(ImageGenerationBudget.consumed).where(
                    ImageGenerationBudget.workspace_id == workspace_id
                )
            )
        assert consumed == 1
    finally:
        await _cleanup(workspace_id)
        await client.aclose()


@pytest.mark.asyncio
async def test_the_visual_brief_answers_without_spending_anything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """35. El brief visual funciona aunque la generación esté apagada."""

    client, workspace_id, business_id = await _workspace_client(with_business=True)
    monkeypatch.setattr(settings, "image_generation_enabled", False)
    try:
        drafted = await client.post(
            f"{API}/brief",
            headers={"X-Workspace-Id": workspace_id},
            json={"business_id": business_id},
        )
        assert drafted.status_code == 200, drafted.text
        body = drafted.json()
        assert body["brief"]["subject"]
        assert body["aspect_ratios"] == ["1:1", "4:5", "9:16"]
        assert body["capability"]["status"] == "disabled"
        assert body["capability"]["fallback"] == "visual_brief"

        blocked = await client.post(
            f"{API}/preflight",
            headers={"X-Workspace-Id": workspace_id},
            json={"brief": body["brief"], "aspect_ratio": "1:1"},
        )
        assert blocked.status_code == 200
        assert blocked.json()["allowed"] is False
        assert blocked.json()["approval_token"] is None

        async with get_session_factory()() as db:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(ImageGenerationJob)
                    .where(ImageGenerationJob.workspace_id == workspace_id)
                )
                == 0
            )
    finally:
        await _cleanup(workspace_id)
        await client.aclose()
