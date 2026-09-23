"""WAVE-011 — durabilidad del job: una imagen, un cobro, una sola vez.

Estas pruebas corren sobre SQLite, que ignora ``FOR UPDATE``. Por eso lo que se
afirma aquí es el *predicado* de reclamo (qué filas son reclamables y cuándo),
no el bloqueo de fila: la exclusión mutua real entre dos workers se verifica en
``tests/e2e/test_image_generation_e2e.py`` contra PostgreSQL.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import delete, func, select

from app.assets.models import Asset, AssetAnalysis
from app.business.models import Business
from app.conversations.models import IdempotencyRecord
from app.core.capabilities import (
    Capability,
    CapabilityStatus,
    get_runtime_capability_registry,
)
from app.core.config import settings
from app.core.errors import AppError
from app.identity.models import AccountPurgeJob, Workspace
from app.identity.purge import execute_purge
from app.images import service as image_service
from app.images.brief import compose_negative_prompt, compose_prompt, normalize_brief
from app.images.models import ImageGenerationBudget, ImageGenerationJob
from app.images.signing import request_fingerprint, sign_preflight
from app.providers.images import GeneratedImage, ImageGenerationRequest
from app.providers.storage import get_object_storage_provider
from tests.conftest import _TestingSessionFactory

WORKSPACE_ID = "ws_test_001"
USER_ID = "usr_test_001"
HEADERS = {"X-Workspace-Id": WORKSPACE_ID}
API = "/api/v1/images"

BRIEF = {
    "subject": "Bandeja de pan dulce recién horneado",
    "setting": "Mostrador de una panadería",
    "style": "Fotografía cenital",
    "palette": "Tonos tierra",
    "mood": "acogedor",
    "avoid": "Manos borrosas",
}


def _png(width: int = 16, height: int = 16) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (180, 140, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


class _CountingProvider:
    """Counts every crossing of the provider boundary."""

    provider_name = "demo"
    model_name = "demo-image-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, request: ImageGenerationRequest) -> GeneratedImage:
        self.calls += 1
        return GeneratedImage(
            content=_png(),
            mime_type="image/png",
            provider_name=self.provider_name,
            model=self.model_name,
            usage_metadata={"provider": self.provider_name, "model": self.model_name},
        )


class _FailingProvider:
    """Fails at the provider, i.e. after the call was already issued."""

    provider_name = "demo"
    model_name = "demo-image-v1"

    def __init__(self, error: AppError) -> None:
        self.calls = 0
        self._error = error

    async def generate(self, *, request: ImageGenerationRequest) -> GeneratedImage:
        self.calls += 1
        raise self._error


class _BrokenStorage:
    """Local storage whose writes fail, to prove nothing is marked completed."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def put(self, *, key: str, content: bytes, content_type: str) -> str:
        raise RuntimeError("disco lleno")

    async def read(self, *, key: str) -> bytes:
        raise FileNotFoundError(key)

    async def delete(self, *, key: str) -> None:
        self.deleted.append(key)

    async def exists(self, *, key: str) -> bool:
        return False

    async def ensure_available(self) -> None:
        return None


def _approval(
    *,
    aspect_ratio: str = "1:1",
    reference_asset_id: str | None = None,
    brief: dict | None = None,
) -> str:
    normalized = normalize_brief(brief or BRIEF)
    return sign_preflight(
        workspace_id=WORKSPACE_ID,
        request_hash=request_fingerprint(
            prompt=compose_prompt(normalized, aspect_ratio=aspect_ratio),
            # What the user asked to avoid is part of the approval: it reaches
            # the provider, so changing it must invalidate the signature.
            negative_prompt=compose_negative_prompt(normalized),
            aspect_ratio=aspect_ratio,
            reference_asset_id=reference_asset_id,
        ),
    ).token


async def _create_job(
    client: AsyncClient,
    *,
    key: str,
    brief: dict | None = None,
    aspect_ratio: str = "1:1",
    confirmed: bool = True,
    approval_token: str | None = None,
    project_id: str | None = None,
):
    payload = {
        "brief": brief or BRIEF,
        "aspect_ratio": aspect_ratio,
        "reference_asset_id": None,
        "approval_token": approval_token or _approval(aspect_ratio=aspect_ratio),
        "confirmed": confirmed,
        "project_id": project_id,
    }
    return await client.post(
        f"{API}/jobs", headers={**HEADERS, "Idempotency-Key": key}, json=payload
    )


async def _claim() -> ImageGenerationJob | None:
    async with _TestingSessionFactory() as db:
        return await image_service.claim_next_job(db)


async def _run_worker(*, user_id: str | None = None) -> ImageGenerationJob | None:
    """One worker pass: claim in a session, execute in that same session."""

    async with _TestingSessionFactory() as db:
        job = await image_service.claim_next_job(db)
        if job is None:
            return None
        return await image_service.execute_job(db, job, user_id=user_id)


async def _reload(job_id: str) -> ImageGenerationJob | None:
    async with _TestingSessionFactory() as db:
        return await db.get(ImageGenerationJob, job_id)


async def _consumed() -> int:
    async with _TestingSessionFactory() as db:
        row = await db.scalar(
            select(ImageGenerationBudget).where(
                ImageGenerationBudget.workspace_id == WORKSPACE_ID
            )
        )
    return row.consumed if row else 0


async def _asset_count() -> int:
    async with _TestingSessionFactory() as db:
        return int(await db.scalar(select(func.count()).select_from(Asset)) or 0)


@pytest_asyncio.fixture(autouse=True)
async def image_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "image_generation_enabled", True)
    monkeypatch.setattr(settings, "image_provider", "demo")
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "object_storage_provider", "local")
    monkeypatch.setattr(settings, "object_storage_local_dir", str(tmp_path / "storage"))
    get_runtime_capability_registry()._outcome_store.clear(Capability.IMAGE_GENERATION)
    async with _TestingSessionFactory() as db:
        for model in (
            ImageGenerationJob,
            ImageGenerationBudget,
            IdempotencyRecord,
            AssetAnalysis,
            Asset,
            Business,
            AccountPurgeJob,
        ):
            await db.execute(delete(model))
        await db.commit()


# --- 20, 21 · idempotencia ---------------------------------------------------


@pytest.mark.asyncio
async def test_repeating_a_confirmation_creates_exactly_one_job(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """20. Creación idempotente."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    first = await _create_job(client, key="key-idem")
    assert first.status_code == 202
    second = await _create_job(client, key="key-idem")
    assert second.status_code == 202
    # Byte-identical replay, including the timestamps.
    assert second.json() == first.json()

    async with _TestingSessionFactory() as db:
        assert int(await db.scalar(select(func.count()).select_from(ImageGenerationJob))) == 1
    # A double click costs one unit, not two.
    assert await _consumed() == 1

    # And the replay does not enqueue a second generation either.
    assert await _run_worker() is not None
    assert await _run_worker() is None
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_the_same_key_with_a_different_payload_conflicts(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """21. Misma key con payload distinto produce conflicto."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    first = await _create_job(client, key="key-shared")
    assert first.status_code == 202

    # Same key, different brief: the client is confused, so nothing happens.
    changed_brief = await _create_job(
        client, key="key-shared", brief={**BRIEF, "subject": "Otro sujeto distinto"}
    )
    assert changed_brief.status_code == 409
    assert changed_brief.json()["error"]["code"] == "CONFLICT"

    # Same key, different format: also a conflict.
    changed_ratio = await _create_job(client, key="key-shared", aspect_ratio="9:16")
    assert changed_ratio.status_code == 409

    async with _TestingSessionFactory() as db:
        assert int(await db.scalar(select(func.count()).select_from(ImageGenerationJob))) == 1
    assert await _consumed() == 1


# --- 22..24 · reclamo, recuperación y terminalidad --------------------------


@pytest.mark.asyncio
async def test_a_second_worker_finds_nothing_to_claim(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """22. Dos workers generan una sola llamada.

    En SQLite se comprueba el predicado: en cuanto el primer worker confirma el
    reclamo, la fila deja de ser reclamable y el segundo worker no encuentra
    trabajo. La exclusión mutua bajo concurrencia real está en el e2e Postgres.
    """

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-two-workers")
    assert created.status_code == 202
    job_id = created.json()["id"]

    claimed = await _claim()
    assert claimed is not None
    assert claimed.id == job_id
    assert claimed.status == "running"
    assert claimed.attempt_count == 1

    # The second worker arrives while the first is still generating.
    assert await _claim() is None

    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        assert job is not None
        await image_service.execute_job(db, job)

    assert provider.calls == 1
    assert (await _reload(job_id)).status == "succeeded"
    assert await _asset_count() == 1


@pytest.mark.asyncio
async def test_an_abandoned_job_is_reclaimed_after_the_grace_period(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """23. Job abandonado se recupera."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-abandoned")
    job_id = created.json()["id"]

    claimed = await _claim()
    assert claimed is not None and claimed.status == "running"

    # A worker that dies mid-flight leaves a running row and no heartbeat.
    assert await _claim() is None

    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        job.started_at = datetime.now(UTC) - timedelta(
            seconds=settings.image_generation_stuck_after_seconds + 60
        )
        await db.commit()

    recovered = await _claim()
    assert recovered is not None
    assert recovered.id == job_id
    assert recovered.attempt_count == 2

    # The recovery is bounded: after max attempts the job is closed, not looped.
    monkeypatch.setattr(settings, "image_generation_max_attempts", 2)
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        job.started_at = datetime.now(UTC) - timedelta(
            seconds=settings.image_generation_stuck_after_seconds + 60
        )
        await db.commit()
    assert await _claim() is None
    stalled = await _reload(job_id)
    assert stalled.status == "failed"
    assert stalled.last_error_code == "IMAGE_MAX_ATTEMPTS"
    assert provider.calls == 0


@pytest.mark.asyncio
async def test_a_completed_job_is_never_claimed_again(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """24. Job completado no se repite."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-terminal")
    job_id = created.json()["id"]

    finished = await _run_worker()
    assert finished is not None and finished.status == "succeeded"

    # Not now, and not after the stuck window either: succeeded is terminal.
    assert await _claim() is None
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        job.started_at = datetime.now(UTC) - timedelta(days=7)
        await db.commit()
    assert await _claim() is None

    assert provider.calls == 1
    assert await _asset_count() == 1
    assert await _consumed() == 1


# --- 25..28 · dinero, fallos y almacenamiento -------------------------------


@pytest.mark.asyncio
async def test_a_failure_before_the_provider_returns_the_reservation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """25. Fallo antes del proveedor no consume presupuesto."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-before-provider")
    job_id = created.json()["id"]
    assert await _consumed() == 1

    # The capability is switched off between the confirmation and the worker.
    def unavailable(**_):
        raise AppError(
            "CAPABILITY_UNAVAILABLE",
            "La generación de imágenes no está disponible.",
            status_code=503,
        )

    monkeypatch.setattr(image_service, "get_image_generation_provider", unavailable)
    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.last_error_code == "CAPABILITY_UNAVAILABLE"
    assert job.asset_id is None
    assert provider.calls == 0
    # Nothing was issued upstream, so the unit goes back.
    assert await _consumed() == 0
    assert await _asset_count() == 0
    assert (await _reload(job_id)).status == "failed"


@pytest.mark.asyncio
async def test_a_failure_after_the_provider_keeps_the_reservation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """26. Fallo después del proveedor conserva la reserva."""

    provider = _FailingProvider(
        AppError(
            "IMAGE_PROVIDER_REJECTED",
            "El proveedor rechazó la solicitud de imagen.",
            status_code=502,
        )
    )
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    created = await _create_job(client, key="key-after-provider")
    assert await _consumed() == 1

    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.last_error_code == "IMAGE_PROVIDER_REJECTED"
    assert provider.calls == 1
    # The call was already issued: refunding it would be inventing credit.
    assert await _consumed() == 1

    read = await client.get(f"{API}/jobs/{created.json()['id']}", headers=HEADERS)
    assert read.json()["image_url"] is None


@pytest.mark.asyncio
async def test_a_storage_failure_is_terminal_and_never_buys_the_image_twice(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """27. Storage failure no marca completed, y tampoco vuelve al proveedor.

    Un disco lleno ocurre *después* de la llamada: el gasto ya existe. El job se
    cierra como fallido con un código propio, la reserva se conserva y —esto es
    lo importante— el paso del tiempo no lo devuelve a la cola.
    """

    provider = _CountingProvider()
    storage = _BrokenStorage()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    monkeypatch.setattr(image_service, "get_object_storage_provider", lambda: storage)

    created = await _create_job(client, key="key-storage-fail")
    job_id = created.json()["id"]

    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.last_error_code == "IMAGE_STORAGE_ERROR"
    assert job.asset_id is None
    assert provider.calls == 1
    assert await _asset_count() == 0
    # El proveedor fue alcanzado: la unidad se queda gastada.
    assert await _consumed() == 1
    # Y el mensaje persistido es la frase de producto, no la excepción interna.
    assert "disco" not in (job.last_error or "")

    # Se mueve el reloj más allá de la ventana de atasco: un fallo posterior al
    # proveedor es terminal, así que nadie lo vuelve a reclamar.
    async with _TestingSessionFactory() as db:
        stored = await db.get(ImageGenerationJob, job_id)
        stored.started_at = datetime.now(UTC) - timedelta(
            seconds=settings.image_generation_stuck_after_seconds + 600
        )
        stored.provider_started_at = stored.started_at
        await db.commit()

    assert await _claim() is None
    assert await _run_worker() is None
    assert provider.calls == 1
    assert (await _reload(job_id)).last_error_code == "IMAGE_STORAGE_ERROR"
    assert await _consumed() == 1

    read = await client.get(f"{API}/jobs/{job_id}", headers=HEADERS)
    assert read.status_code == 200
    assert read.json()["status"] == "failed"
    assert read.json()["image_url"] is None


@pytest.mark.asyncio
async def test_a_worker_that_dies_past_the_boundary_never_re_issues_the_call(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El límite pagado es durable: `provider_started` no se reclama jamás.

    Se simula el peor caso: el worker cruzó el límite y desapareció. El registro
    queda en `provider_started` para siempre a menos que alguien lo cierre, y lo
    que lo cierra es el barrido —con un código ambiguo y sin devolver dinero—,
    nunca un segundo intento.
    """

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-boundary")
    job_id = created.json()["id"]

    claimed = await _claim()
    assert claimed is not None
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        assert await image_service._mark_provider_started(db, job, token=job.claim_token)
    crossed = await _reload(job_id)
    assert crossed.status == "provider_started"
    assert crossed.provider_started_at is not None

    # Aunque el lease haya vencido con creces, la fila no es reclamable.
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        stale = datetime.now(UTC) - timedelta(
            seconds=settings.image_generation_stuck_after_seconds + 600
        )
        job.started_at = stale
        job.provider_started_at = stale
        await db.commit()

    assert await _run_worker() is None
    assert provider.calls == 0

    swept = await _reload(job_id)
    assert swept.status == "failed"
    assert swept.last_error_code == "IMAGE_EXECUTION_UNKNOWN"
    assert swept.claim_token is None
    # Nadie sabe si el proveedor cobró, así que inventar un reembolso sería
    # regalar crédito en cada hipo de la red.
    assert await _consumed() == 1
    assert await _asset_count() == 0


@pytest.mark.asyncio
async def test_a_late_worker_cannot_overwrite_a_decided_job(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El token de reclamo es una valla: quien lo perdió ya no escribe nada."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-fenced")
    job_id = created.json()["id"]

    claimed = await _claim()
    assert claimed is not None
    stale_token = claimed.claim_token

    # Otro actor decide el job mientras este worker seguía "vivo".
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        job.status = "failed"
        job.completed_at = datetime.now(UTC)
        job.last_error_code = "IMAGE_EXECUTION_UNKNOWN"
        job.claim_token = None
        await db.commit()

    # El worker rezagado intenta cerrar con su token viejo: no gana la escritura.
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
        await image_service._fail(
            db,
            job,
            token=stale_token,
            code="IMAGE_PROVIDER_REJECTED",
            message="El proveedor rechazó la solicitud de imagen.",
            refund=True,
        )

    final = await _reload(job_id)
    assert final.last_error_code == "IMAGE_EXECUTION_UNKNOWN"
    # Y tampoco reembolsa: la reserva no era suya para devolverla.
    assert await _consumed() == 1


@pytest.mark.asyncio
async def test_a_refund_returns_to_the_period_that_paid(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3. Un job de ayer que falla hoy devuelve la unidad al día que la cobró."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    # Se confirma justo antes de la medianoche UTC.
    yesterday = datetime.now(UTC).replace(hour=23, minute=59, second=0, microsecond=0) - timedelta(
        days=1
    )
    async with _TestingSessionFactory() as db:
        old_job = await image_service.create_job(
            db,
            workspace_id=WORKSPACE_ID,
            brief_payload=BRIEF,
            aspect_ratio="1:1",
            approval_token=_approval(),
            confirmed=True,
            now=yesterday,
        )
        await db.commit()
        old_job_id = old_job.id
        old_budget_id = old_job.budget_id

    # Y ya en el día nuevo hay consumo legítimo de otro usuario del workspace.
    today = await _create_job(client, key="key-today")
    assert today.status_code == 202

    async with _TestingSessionFactory() as db:
        rows = {
            row.id: row.consumed
            for row in (await db.scalars(select(ImageGenerationBudget))).all()
        }
    assert len(rows) == 2
    today_budget_id = next(key for key in rows if key != old_budget_id)
    assert rows[old_budget_id] == 1
    assert rows[today_budget_id] == 1

    # El job de ayer falla antes del proveedor, ya pasada la medianoche.
    def unavailable(**_):
        raise AppError(
            "CAPABILITY_UNAVAILABLE",
            "La generación de imágenes no está disponible.",
            status_code=503,
        )

    monkeypatch.setattr(image_service, "get_image_generation_provider", unavailable)
    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, old_job_id)
        job.status = "running"
        job.started_at = datetime.now(UTC)
        job.claim_token = "token-de-ayer"
        await db.commit()
        job = await db.get(ImageGenerationJob, old_job_id)
        await image_service.execute_job(db, job)

    async with _TestingSessionFactory() as db:
        rows = {
            row.id: row.consumed
            for row in (await db.scalars(select(ImageGenerationBudget))).all()
        }
    # La reserva vuelve al período que la tomó...
    assert rows[old_budget_id] == 0
    # ...y el consumo del día nuevo queda intacto.
    assert rows[today_budget_id] == 1
    assert (await _reload(old_job_id)).status == "failed"


@pytest.mark.asyncio
async def test_the_worker_runs_the_route_the_job_recorded(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Un cambio de configuración no mueve el gasto a otro modelo."""

    # La fábrica real, envuelta para observar con qué ruta se la invoca.
    real_factory = image_service.get_image_generation_provider
    seen: list[tuple[str | None, str | None]] = []

    def spy(*, provider=None, model=None):
        seen.append((provider, model))
        return real_factory(provider=provider, model=model)

    monkeypatch.setattr(image_service, "get_image_generation_provider", spy)

    created = await _create_job(client, key="key-route")
    job_id = created.json()["id"]
    # La confirmación registra "lo que se ejecutaría ahora".
    assert seen == [(None, None)]

    async with _TestingSessionFactory() as db:
        job = await db.get(ImageGenerationJob, job_id)
    assert job.provider == "demo"
    assert job.model == "demo-image-v1"

    # Entre la confirmación y el worker, la configuración cambia de modelo.
    monkeypatch.setattr(settings, "image_generation_model", "otro/modelo-caro")
    monkeypatch.setattr(settings, "image_provider", "openrouter")

    finished = await _run_worker()
    assert finished is not None and finished.status == "succeeded"
    # El worker pide exactamente la ruta persistida, no la configurada hoy.
    assert seen[1:] == [("demo", "demo-image-v1")]

    async with _TestingSessionFactory() as db:
        stored = await db.get(ImageGenerationJob, job_id)
        asset = await db.get(Asset, stored.asset_id)
    assert stored.provider == "demo"
    assert stored.model == "demo-image-v1"
    assert asset is not None


@pytest.mark.asyncio
async def test_a_route_that_is_no_longer_authorized_fails_before_the_provider(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5b. Ruta desautorizada: falla antes de gastar y devuelve la reserva."""

    real_factory = image_service.get_image_generation_provider
    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    created = await _create_job(client, key="key-route-revoked")
    job_id = created.json()["id"]
    assert await _consumed() == 1

    # El worker usa la fábrica real, y la ruta demo deja de estar autorizada.
    monkeypatch.setattr(image_service, "get_image_generation_provider", real_factory)
    monkeypatch.setattr(settings, "app_env", "production")

    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.last_error_code == "IMAGE_PROVIDER_UNAVAILABLE"
    assert provider.calls == 0
    assert await _consumed() == 0
    assert (await _reload(job_id)).asset_id is None


@pytest.mark.asyncio
async def test_a_vanished_reference_is_never_generated_without(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6. Sin la referencia aprobada no se genera nada."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    async with _TestingSessionFactory() as db:
        asset = Asset(
            workspace_id=WORKSPACE_ID,
            original_name="referencia.png",
            storage_path=f"workspaces/{WORKSPACE_ID}/uploads/referencia.png",
            mime_type="image/png",
            file_size_bytes=len(_png()),
            asset_type="image",
            width=16,
            height=16,
        )
        db.add(asset)
        await db.commit()
        reference_id = asset.id
    await get_object_storage_provider().put(
        key=f"workspaces/{WORKSPACE_ID}/uploads/referencia.png",
        content=_png(),
        content_type="image/png",
    )

    response = await client.post(
        f"{API}/jobs",
        headers={**HEADERS, "Idempotency-Key": "key-reference"},
        json={
            "brief": BRIEF,
            "aspect_ratio": "1:1",
            "reference_asset_id": reference_id,
            "approval_token": _approval(reference_asset_id=reference_id),
            "confirmed": True,
            "project_id": None,
        },
    )
    assert response.status_code == 202
    assert await _consumed() == 1

    # La referencia desaparece entre la confirmación y el worker.
    async with _TestingSessionFactory() as db:
        await db.execute(delete(Asset).where(Asset.id == reference_id))
        await db.commit()

    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.last_error_code == "IMAGE_REFERENCE_UNAVAILABLE"
    # Nada salió del proceso, así que la unidad vuelve.
    assert provider.calls == 0
    assert await _consumed() == 0
    assert await _asset_count() == 0


@pytest.mark.asyncio
async def test_an_image_of_the_wrong_shape_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """9. Una respuesta cuadrada a un 9:16 no es la imagen aprobada."""

    class _SquareProvider(_CountingProvider):
        async def generate(self, *, request: ImageGenerationRequest) -> GeneratedImage:
            self.calls += 1
            return GeneratedImage(
                content=_png(512, 512),
                mime_type="image/png",
                provider_name=self.provider_name,
                model=self.model_name,
                usage_metadata={},
            )

    provider = _SquareProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    created = await _create_job(client, key="key-shape", aspect_ratio="9:16")
    assert created.status_code == 202
    job_id = created.json()["id"]

    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.last_error_code == "IMAGE_PROVIDER_INVALID_RESPONSE"
    assert provider.calls == 1
    # No se guarda una imagen con un formato distinto al que declara el job.
    assert await _asset_count() == 0
    assert (await _reload(job_id)).asset_id is None
    # El gasto ya ocurrió: la reserva no se devuelve.
    assert await _consumed() == 1


@pytest.mark.asyncio
async def test_changing_what_to_avoid_invalidates_the_approval(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4. `avoid` forma parte de lo aprobado y de lo que llega al proveedor."""

    captured: list[ImageGenerationRequest] = []

    class _RecordingProvider(_CountingProvider):
        async def generate(self, *, request: ImageGenerationRequest) -> GeneratedImage:
            captured.append(request)
            return await super().generate(request=request)

    provider = _RecordingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    approved = {**BRIEF, "avoid": "Manos borrosas y texto ilegible"}
    tampered = {**BRIEF, "avoid": "Ninguna restriccion"}
    token = _approval(brief=approved)

    # Se reutiliza el token aprobado con otro `avoid`: la firma ya no cubre eso.
    reused = await _create_job(
        client, key="key-avoid-swap", brief=tampered, approval_token=token
    )
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "IMAGE_PREFLIGHT_REQUIRED"
    assert await _consumed() == 0

    # Con el brief realmente aprobado sí procede, y el proveedor recibe la
    # restricción confirmada: no es un campo que se guarde y se ignore.
    accepted = await _create_job(
        client, key="key-avoid-ok", brief=approved, approval_token=token
    )
    assert accepted.status_code == 202
    job = await _run_worker()
    assert job is not None and job.status == "succeeded"
    assert len(captured) == 1
    assert captured[0].negative_prompt == "Manos borrosas y texto ilegible"

    async with _TestingSessionFactory() as db:
        stored = await db.get(ImageGenerationJob, accepted.json()["id"])
    assert stored.negative_prompt == "Manos borrosas y texto ilegible"


@pytest.mark.asyncio
async def test_a_success_stores_private_bytes_outside_the_database(
    client: AsyncClient,
) -> None:
    """28. Success almacena bytes privados."""

    created = await _create_job(client, key="key-success")
    job_id = created.json()["id"]
    job = await _run_worker(user_id=USER_ID)
    assert job is not None and job.status == "succeeded"

    async with _TestingSessionFactory() as db:
        asset = await db.get(Asset, job.asset_id)
    assert asset is not None
    assert asset.workspace_id == WORKSPACE_ID
    assert asset.asset_type == "image"
    assert asset.storage_path == f"workspaces/{WORKSPACE_ID}/generated/{job_id}.png"

    stored = await get_object_storage_provider().read(key=asset.storage_path)
    assert stored[:8] == b"\x89PNG\r\n\x1a\n"
    assert asset.file_size_bytes == len(stored)

    # The bytes live under the workspace prefix on disk, never in a public dir.
    on_disk = Path(settings.object_storage_local_dir) / asset.storage_path
    assert on_disk.is_file()
    assert on_disk.read_bytes() == stored

    # And they are only reachable through a signed link.
    assert (await client.get(f"{API}/files/{asset.id}")).status_code == 403
    read = await client.get(f"{API}/jobs/{job_id}", headers=HEADERS)
    assert (await client.get(read.json()["image_url"])).status_code == 200


# --- 33, 34 · limpieza y reintento ------------------------------------------


@pytest.mark.asyncio
async def test_account_cleanup_removes_jobs_budget_and_generated_assets(
    client: AsyncClient,
) -> None:
    """33. Account/project cleanup contempla los assets."""

    created = await _create_job(client, key="key-purge")
    job_id = created.json()["id"]
    job = await _run_worker()
    assert job is not None and job.status == "succeeded"

    async with _TestingSessionFactory() as db:
        asset = await db.get(Asset, job.asset_id)
    storage_path = asset.storage_path
    assert await get_object_storage_provider().exists(key=storage_path)

    async with _TestingSessionFactory() as db:
        purge = AccountPurgeJob(
            id="apj_image_001",
            user_id=USER_ID,
            workspace_id=WORKSPACE_ID,
            status="processing",
            started_at=datetime.now(UTC),
        )
        db.add(purge)
        await db.commit()
        finished = await execute_purge(db, purge)
    assert finished.status == "completed"
    assert finished.last_error is None

    async with _TestingSessionFactory() as db:
        assert await db.get(ImageGenerationJob, job_id) is None
        assert await db.get(Asset, asset.id) is None
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ImageGenerationBudget)
                .where(ImageGenerationBudget.workspace_id == WORKSPACE_ID)
            )
        ) == 0
    # The generated bytes are gone from storage too, not just from the index.
    assert await get_object_storage_provider().exists(key=storage_path) is False


@pytest.mark.asyncio
async def test_retrying_a_generation_never_duplicates_the_asset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """34. Retry no duplica asset."""

    provider = _CountingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    created = await _create_job(client, key="key-retry")
    job_id = created.json()["id"]
    job = await _run_worker()
    assert job is not None and job.status == "succeeded"
    asset_id = job.asset_id

    # A retry with the same key replays: same job, same asset, no second call.
    replay = await _create_job(client, key="key-retry")
    assert replay.status_code == 202
    assert replay.json()["id"] == job_id
    assert await _run_worker() is None
    assert provider.calls == 1
    assert await _asset_count() == 1
    assert (await _reload(job_id)).asset_id == asset_id
    assert await _consumed() == 1

    # A genuine retry after a failure is a new job with a new key, and it never
    # touches the asset the first attempt produced.
    failing = _FailingProvider(
        AppError("IMAGE_PROVIDER_TIMEOUT", "Tardó demasiado.", status_code=504, retryable=True)
    )
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: failing)
    second = await _create_job(client, key="key-retry-2")
    second_id = second.json()["id"]
    assert second_id != job_id
    assert (await _run_worker()).status == "failed"
    assert await _asset_count() == 1

    # A timeout reports reduced capacity, not an outage: the user can retry.
    degraded = get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION)
    assert degraded.status is CapabilityStatus.DEGRADED

    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)
    third = await _create_job(client, key="key-retry-3")
    assert (await _run_worker()).status == "succeeded"
    assert await _asset_count() == 2
    assert (await _reload(third.json()["id"])).asset_id != asset_id
    # Three confirmations, three units: a retry is a new generation, not a free one.
    assert await _consumed() == 3


@pytest.mark.asyncio
async def test_an_unconfirmed_request_never_becomes_a_job(client: AsyncClient) -> None:
    """La confirmación explícita es una precondición, no una casilla decorativa."""

    response = await _create_job(client, key="key-unconfirmed", confirmed=False)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert await _consumed() == 0
    async with _TestingSessionFactory() as db:
        assert await db.scalar(select(ImageGenerationJob)) is None

    # The key stays usable, because nothing was spent under it.
    retried = await _create_job(client, key="key-unconfirmed", confirmed=True)
    assert retried.status_code == 202


@pytest.mark.asyncio
async def test_a_missing_idempotency_key_is_refused(client: AsyncClient) -> None:
    """Sin clave de idempotencia no hay job: el reintento no sería seguro."""

    response = await client.post(
        f"{API}/jobs",
        headers=HEADERS,
        json={
            "brief": BRIEF,
            "aspect_ratio": "1:1",
            "reference_asset_id": None,
            "approval_token": _approval(),
            "confirmed": True,
            "project_id": None,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert await _consumed() == 0


@pytest.mark.asyncio
async def test_a_job_of_another_workspace_is_not_readable(client: AsyncClient) -> None:
    """El polling está acotado al workspace del que confirmó la generación."""

    created = await _create_job(client, key="key-tenant")
    job_id = created.json()["id"]

    async with _TestingSessionFactory() as db:
        if await db.get(Workspace, "ws_other_001") is None:
            db.add(Workspace(id="ws_other_001", name="Otro workspace"))
            await db.commit()

    foreign = await client.get(f"{API}/jobs/{job_id}", headers={"X-Workspace-Id": "ws_other_001"})
    assert foreign.status_code in {403, 404}
