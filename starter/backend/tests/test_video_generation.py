"""WAVE-013 — generación de video asíncrona, acotada y privada."""

from __future__ import annotations

import struct
from importlib import resources
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.assets.models import Asset, AssetAnalysis
from app.business.models import BrandProfile, Business
from app.conversations.models import AIUsageEvent, IdempotencyRecord
from app.core.capabilities import Capability, get_runtime_capability_registry
from app.core.config import settings
from app.core.errors import ValidationError_
from app.identity.models import AccountPurgeJob
from app.projects.models import Project
from app.providers.video import (
    DemoVideoGenerationProvider,
    VideoGenerationRequest,
    VideoJobState,
    VideoSubmission,
)
from app.videos import service as video_service
from app.videos import worker as video_worker
from app.videos.models import VideoGenerationBudget, VideoGenerationJob
from app.videos.validation import VideoValidationError, validate_video_bytes
from tests.conftest import _TestingSessionFactory

WORKSPACE_ID = "ws_test_001"
USER_ID = "usr_test_001"
HEADERS = {"X-Workspace-Id": WORKSPACE_ID}
API = "/api/v1/videos"

STORYBOARD = {
    "hook": "Una idea clara para tu negocio",
    "duration_seconds": 5,
    "aspect_ratio": "9:16",
    "voiceover": "Descubre una propuesta pensada para ti.",
    "music_direction": "Ritmo cálido y limpio.",
    "shots": [
        {
            "order": 1,
            "duration_seconds": 2,
            "visual": "Producto en primer plano.",
            "camera": "Acercamiento estable.",
            "on_screen_text": "Conócenos",
            "voiceover": "Presentamos una opción clara.",
            "transition": "Corte limpio",
        },
        {
            "order": 2,
            "duration_seconds": 2,
            "visual": "Detalle del producto en uso.",
            "camera": "Movimiento vertical suave.",
            "on_screen_text": "Pensado para ti",
            "voiceover": "Una propuesta práctica para tu día.",
            "transition": "Disolvencia breve",
        },
        {
            "order": 3,
            "duration_seconds": 1,
            "visual": "Cierre con identidad del negocio.",
            "camera": "Plano medio vertical.",
            "on_screen_text": "Escríbenos",
            "voiceover": "Da el siguiente paso.",
            "transition": "Cierre suave",
        },
    ],
}


def _request(duration_seconds: int = 5) -> VideoGenerationRequest:
    storyboard = {**STORYBOARD, "duration_seconds": duration_seconds}
    return VideoGenerationRequest(
        prompt="Genera un clip vertical de prueba.",
        negative_prompt="Sin texto ilegible.",
        storyboard=storyboard,
        aspect_ratio="9:16",
        duration_seconds=duration_seconds,
        model="",
        source_image=None,
        source_image_mime=None,
    )


def _preflight_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "storyboard": STORYBOARD,
        "prompt": "Genera un clip vertical de prueba.",
        "negative_prompt": "Sin texto ilegible.",
        "duration_seconds": 5,
        "source_asset_id": None,
        "project_id": None,
    }
    payload.update(overrides)
    return payload


async def _approved_payload(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json=_preflight_payload(),
    )
    assert response.status_code == 200, response.text
    preflight = response.json()
    assert preflight["allowed"] is True
    assert preflight["approval_token"]
    return {
        **_preflight_payload(),
        "confirmed": True,
        "approval_token": preflight["approval_token"],
    }


async def _create_job(client: AsyncClient, *, key: str) -> tuple[str, dict[str, object]]:
    payload = await _approved_payload(client)
    response = await client.post(
        f"{API}/jobs",
        headers={**HEADERS, "Idempotency-Key": key},
        json=payload,
    )
    assert response.status_code == 202, response.text
    return response.json()["id"], payload


async def _run_worker_pass(*, user_id: str | None = None) -> VideoGenerationJob | None:
    async with _TestingSessionFactory() as db:
        job = await video_worker.claim_next_job(db)
        if job is None:
            return None
        return await video_worker.execute_job(db, job, user_id=user_id)


async def _reload(job_id: str) -> VideoGenerationJob:
    async with _TestingSessionFactory() as db:
        job = await db.get(VideoGenerationJob, job_id)
        assert job is not None
        return job


async def _consumed() -> int:
    async with _TestingSessionFactory() as db:
        row = await db.scalar(
            select(VideoGenerationBudget).where(VideoGenerationBudget.workspace_id == WORKSPACE_ID)
        )
        return row.consumed if row else 0


def _fixture_video() -> bytes:
    return resources.files("app.videos.fixtures").joinpath("demo-9x16-5s.mp4").read_bytes()


def _top_level_boxes(content: bytes) -> list[tuple[bytes, int, int]]:
    boxes: list[tuple[bytes, int, int]] = []
    offset = 0
    while offset < len(content):
        size = struct.unpack_from(">I", content, offset)[0]
        if size == 1:
            size = struct.unpack_from(">Q", content, offset + 8)[0]
        if size < 8 or offset + size > len(content):
            raise AssertionError("fixture MP4 inválida")
        boxes.append((content[offset + 4 : offset + 8], offset, offset + size))
        offset += size
    return boxes


def _remove_top_level_box(content: bytes, kind: bytes) -> bytes:
    for candidate, start, end in _top_level_boxes(content):
        if candidate == kind:
            return content[:start] + content[end:]
    raise AssertionError(f"No se encontró {kind!r}")


def _mutate_tkhd_dimensions(content: bytes, width: int, height: int) -> bytes:
    mutated = bytearray(content)
    marker = mutated.find(b"tkhd")
    assert marker >= 4
    box_start = marker - 4
    box_size = struct.unpack_from(">I", mutated, box_start)[0]
    struct.pack_into(">II", mutated, box_start + box_size - 8, width << 16, height << 16)
    return bytes(mutated)


@pytest_asyncio.fixture(autouse=True)
async def video_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "video_generation_enabled", True)
    monkeypatch.setattr(settings, "video_provider", "demo")
    monkeypatch.setattr(settings, "video_generation_model", "")
    monkeypatch.setattr(settings, "video_generation_allowed_durations", [5, 10])
    monkeypatch.setattr(settings, "video_generation_daily_budget", 2)
    monkeypatch.setattr(settings, "object_storage_provider", "local")
    monkeypatch.setattr(settings, "object_storage_local_dir", str(tmp_path / "storage"))
    get_runtime_capability_registry()._outcome_store.clear(Capability.VIDEO_GENERATION)

    async with _TestingSessionFactory() as db:
        for model in (
            VideoGenerationJob,
            VideoGenerationBudget,
            AIUsageEvent,
            IdempotencyRecord,
            Project,
            AssetAnalysis,
            Asset,
            BrandProfile,
            Business,
            AccountPurgeJob,
        ):
            await db.execute(delete(model))
        await db.commit()


@pytest.mark.asyncio
async def test_demo_download_survives_provider_restart_with_persisted_duration() -> None:
    """La duración no depende de memoria efímera del adaptador."""

    first_process = DemoVideoGenerationProvider()
    submission = await first_process.submit(_request(duration_seconds=10))

    restarted_process = DemoVideoGenerationProvider()
    artifact = await restarted_process.download(
        submission.provider_job_id,
        duration_seconds=10,
    )
    metadata = validate_video_bytes(
        artifact.content,
        declared_mime=artifact.mime_type,
        expected_duration=10,
        expected_ratio=9 / 16,
        max_bytes=settings.video_generation_max_bytes,
    )
    assert metadata.duration_seconds == pytest.approx(10, abs=1)


@pytest.mark.asyncio
async def test_demo_download_rejects_duration_without_an_exact_fixture() -> None:
    provider = DemoVideoGenerationProvider()
    with pytest.raises(ValueError, match="fixture demo exacta"):
        await provider.download("demo-job", duration_seconds=7)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda content: _remove_top_level_box(content, b"mdat"),
        lambda content: content.replace(b"vide", b"soun", 1),
        lambda content: (
            content[: content.find(b"stsd") + 8]
            + content[content.find(b"stsd") + 8 :].replace(b"avc1", b"vp09", 1)
        ),
        lambda content: _mutate_tkhd_dimensions(content, 9_000, 16),
        lambda content: _mutate_tkhd_dimensions(content, 640, 360),
        lambda content: (
            content[: content.find(b"mvhd") + 20]
            + struct.pack(">I", 10_000)
            + content[content.find(b"mvhd") + 24 :]
        ),
        lambda content: content[:-7],
    ],
    ids=[
        "metadata_without_mdat",
        "audio_only",
        "codec_not_allowed",
        "absurd_dimensions",
        "wrong_ratio",
        "wrong_duration",
        "truncated_container",
    ],
)
def test_mp4_validation_rejects_unplayable_or_mismatched_results(mutate) -> None:
    content = mutate(_fixture_video())
    with pytest.raises(VideoValidationError):
        validate_video_bytes(
            content,
            declared_mime="video/mp4",
            expected_duration=5,
            expected_ratio=9 / 16,
            max_bytes=settings.video_generation_max_bytes,
        )


@pytest.mark.asyncio
async def test_preflight_approval_and_idempotency_create_one_bounded_job(
    client: AsyncClient,
) -> None:
    job_id, payload = await _create_job(client, key="video-idempotency")
    replay = await client.post(
        f"{API}/jobs",
        headers={**HEADERS, "Idempotency-Key": "video-idempotency"},
        json=payload,
    )
    assert replay.status_code == 202
    assert replay.json()["id"] == job_id
    assert replay.json()["status"] == "queued"

    changed = {**payload, "prompt": "Otro prompt aprobado no es este."}
    conflict = await client.post(
        f"{API}/jobs",
        headers={**HEADERS, "Idempotency-Key": "video-idempotency"},
        json=changed,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "preflight_invalid"
    assert await _consumed() == 1

    foreign = await client.get(
        f"{API}/jobs/{job_id}",
        headers={"X-Workspace-Id": "ws_foreign_001"},
    )
    assert foreign.status_code == 403

    async with _TestingSessionFactory() as db:
        assert int(await db.scalar(select(func.count()).select_from(VideoGenerationJob))) == 1


@pytest.mark.asyncio
async def test_disabled_video_returns_editable_preflight_fallback_without_approval(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "video_generation_enabled", False)
    get_runtime_capability_registry()._outcome_store.clear(Capability.VIDEO_GENERATION)

    response = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json=_preflight_payload(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is False
    assert body["reason_code"] == "disabled"
    assert body["approval_token"] is None
    assert body["storyboard"]["aspect_ratio"] == "9:16"
    assert await _consumed() == 0


@pytest.mark.asyncio
async def test_daily_budget_blocks_a_second_confirmation(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "video_generation_daily_budget", 1)
    await _create_job(client, key="video-budget-first")

    second_preflight = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json=_preflight_payload(),
    )
    assert second_preflight.status_code == 200
    assert second_preflight.json()["allowed"] is False
    assert second_preflight.json()["reason_code"] == "quota_exhausted"
    assert second_preflight.json()["approval_token"] is None
    assert await _consumed() == 1


@pytest.mark.asyncio
async def test_preflight_rejects_duration_without_an_exact_demo_fixture(
    client: AsyncClient,
) -> None:
    storyboard = {**STORYBOARD, "duration_seconds": 7}
    storyboard["shots"] = [
        {**STORYBOARD["shots"][0]},
        {**STORYBOARD["shots"][1]},
        {**STORYBOARD["shots"][2], "duration_seconds": 3},
    ]
    response = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json=_preflight_payload(storyboard=storyboard, duration_seconds=7),
    )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["reason_code"] == "duration_not_allowed"
    assert await _consumed() == 0


@pytest.mark.asyncio
async def test_storyboard_draft_rejects_duration_outside_server_allowlist() -> None:
    with pytest.raises(ValidationError_):
        await video_service.draft_storyboard(
            None,  # type: ignore[arg-type]
            workspace_id=WORKSPACE_ID,
            business_id="business-not-used",
            publication_text=None,
            trend_title=None,
            duration_seconds=7,
        )


@pytest.mark.asyncio
async def test_demo_worker_persists_private_video_asset_and_usage(
    client: AsyncClient,
) -> None:
    job_id, _ = await _create_job(client, key="video-worker")

    preparing = await _run_worker_pass()
    assert preparing is not None
    assert preparing.status == "provider_pending"
    assert preparing.provider_job_id

    succeeded = await _run_worker_pass()
    assert succeeded is not None
    assert succeeded.status == "succeeded"
    assert succeeded.asset_id
    assert await _consumed() == 1

    response = await client.get(f"{API}/jobs/{job_id}", headers=HEADERS)
    assert response.status_code == 200
    public = response.json()
    assert public["status"] == "succeeded"
    assert public["video_url"]
    assert "provider_job_id" not in public
    assert "storage_path" not in public

    file_response = await client.get(public["video_url"])
    assert file_response.status_code == 200
    assert file_response.headers["accept-ranges"] == "none"
    assert file_response.headers["cache-control"] == "private, no-store"
    assert file_response.content[4:8] == b"ftyp"

    async with _TestingSessionFactory() as db:
        asset = await db.get(Asset, succeeded.asset_id)
        assert asset is not None
        assert asset.asset_type == "video"
        assert asset.duration_seconds == 5
        usage = list(
            await db.scalars(
                select(AIUsageEvent).where(
                    AIUsageEvent.workspace_id == WORKSPACE_ID,
                    AIUsageEvent.capability == Capability.VIDEO_GENERATION.value,
                )
            )
        )
        assert len(usage) == 1
        assert usage[0].reported_cost == 1
        assert usage[0].user_id == USER_ID
        persisted_job = await db.get(VideoGenerationJob, job_id)
        assert persisted_job is not None
        assert persisted_job.requested_by_user_id == USER_ID

    assert await _run_worker_pass() is None


class _PendingProvider:
    name = "demo"

    def __init__(self, pending_calls: int) -> None:
        self.inner = DemoVideoGenerationProvider()
        self.pending_calls = pending_calls
        self.submit_calls = 0
        self.check_calls = 0

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission:
        self.submit_calls += 1
        return await self.inner.submit(request)

    async def check(self, provider_job_id: str) -> VideoJobState:
        self.check_calls += 1
        if self.check_calls <= self.pending_calls:
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

    async def download(self, provider_job_id: str, *, duration_seconds: int):
        return await self.inner.download(
            provider_job_id,
            duration_seconds=duration_seconds,
        )

    async def cancel(self, provider_job_id: str) -> bool:
        _ = provider_job_id
        return False


@pytest.mark.asyncio
async def test_pending_polls_do_not_consume_submit_attempts(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, _ = await _create_job(client, key="video-five-polls")
    provider = _PendingProvider(pending_calls=5)
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)
    monkeypatch.setattr(settings, "video_generation_poll_interval_seconds", 0)

    first = await _run_worker_pass()
    assert first is not None and first.status == "provider_pending"
    for _ in range(5):
        pending = await _run_worker_pass()
        assert pending is not None and pending.status == "provider_pending"
    ready = await _run_worker_pass()

    assert ready is not None and ready.status == "succeeded"
    assert provider.submit_calls == 1
    assert provider.check_calls >= 5
    persisted = await _reload(job_id)
    assert persisted.status == "succeeded"
    assert persisted.attempt_count == 1
    assert persisted.poll_count == 6


@pytest.mark.asyncio
async def test_worker_feature_flag_fails_queued_job_before_provider_and_refunds(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, _ = await _create_job(client, key="video-disabled-after-confirm")
    monkeypatch.setattr(settings, "video_generation_enabled", False)

    def provider_must_not_be_constructed():
        raise AssertionError("no se debe resolver el proveedor antes del submit")

    monkeypatch.setattr(
        video_worker, "get_video_generation_provider", provider_must_not_be_constructed
    )
    failed = await _run_worker_pass()

    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error_code == "capability_unavailable"
    assert await _consumed() == 0


@pytest.mark.asyncio
async def test_run_once_uses_persisted_actor_without_manual_user_id(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id, _ = await _create_job(client, key="video-run-once-actor")
    monkeypatch.setattr(video_worker, "get_session_factory", lambda: _TestingSessionFactory)

    assert await video_worker.run_once(batch=2) == 2
    persisted = await _reload(job_id)
    assert persisted.status == "succeeded"
    async with _TestingSessionFactory() as db:
        usage = await db.scalar(
            select(AIUsageEvent).where(
                AIUsageEvent.workspace_id == WORKSPACE_ID,
                AIUsageEvent.capability == Capability.VIDEO_GENERATION.value,
            )
        )
        assert usage is not None
        assert usage.user_id == USER_ID


class _UnknownCostProvider:
    name = "demo"

    def __init__(self) -> None:
        self._fixture = DemoVideoGenerationProvider()

    async def submit(self, request: VideoGenerationRequest) -> VideoSubmission:
        return await self._fixture.submit(request)

    async def check(self, provider_job_id: str) -> VideoJobState:
        _ = provider_job_id
        return VideoJobState(
            provider_status="ready",
            ready=True,
            failed=False,
            error_code=None,
            error_message=None,
            cost_units=None,
        )

    async def download(self, provider_job_id: str, *, duration_seconds: int):
        return await self._fixture.download(
            provider_job_id,
            duration_seconds=duration_seconds,
        )

    async def cancel(self, provider_job_id: str) -> bool:
        _ = provider_job_id
        return False


@pytest.mark.asyncio
async def test_unknown_provider_cost_is_not_recorded_as_zero(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _create_job(client, key="video-unknown-cost")
    provider = _UnknownCostProvider()
    monkeypatch.setattr(video_worker, "get_video_generation_provider", lambda: provider)

    assert (await _run_worker_pass()) is not None
    succeeded = await _run_worker_pass()
    assert succeeded is not None and succeeded.status == "succeeded"

    async with _TestingSessionFactory() as db:
        usage = await db.scalar(
            select(AIUsageEvent).where(
                AIUsageEvent.workspace_id == WORKSPACE_ID,
                AIUsageEvent.capability == Capability.VIDEO_GENERATION.value,
            )
        )
        assert usage is not None
        assert usage.reported_cost is None
