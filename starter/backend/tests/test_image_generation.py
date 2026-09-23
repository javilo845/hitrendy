"""WAVE-011 — las ocho puertas de una generación de imagen y su fallback.

Nada aquí toca la red: el proveedor OpenRouter se ejercita con
``httpx.MockTransport`` y el proveedor demo renderiza en memoria. Las pruebas
que gastan presupuesto lo hacen contra el ledger local, nunca contra una cuenta
real.
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import delete, select

from app.assets.models import Asset, AssetAnalysis
from app.assets.validation import validate_image_bytes
from app.business.models import Business
from app.conversations.models import IdempotencyRecord
from app.core.capabilities import (
    Capability,
    CapabilityStatus,
    get_runtime_capability_registry,
)
from app.core.config import settings
from app.core.errors import AppError
from app.identity.models import Workspace
from app.images import service as image_service
from app.images.brief import compose_negative_prompt, compose_prompt, normalize_brief
from app.images.models import ImageGenerationBudget, ImageGenerationJob
from app.images.signing import request_fingerprint, sign_image_url, sign_preflight
from app.providers.factory import get_image_generation_provider
from app.providers.images import (
    ASPECT_RATIOS,
    GeneratedImage,
    ImageGenerationRequest,
    OpenRouterImageGenerationProvider,
)
from app.providers.storage import get_object_storage_provider
from tests.conftest import _TestingSessionFactory

WORKSPACE_ID = "ws_test_001"
OTHER_WORKSPACE_ID = "ws_other_001"
HEADERS = {"X-Workspace-Id": WORKSPACE_ID}
API = "/api/v1/images"

#: A key shaped like the real thing so a leak would be unmistakable.
FAKE_API_KEY = "sk-or-v1-test-secret-never-real"

BRIEF = {
    "subject": "Vaso de café frío sobre una mesa de madera",
    "setting": "Cafetería luminosa en Tegucigalpa",
    "style": "Fotografía de producto, luz natural",
    "palette": "Tonos cálidos",
    "mood": "cercano",
    "avoid": "Texto ilegible",
}


# --- helpers ----------------------------------------------------------------


def _png(width: int = 8, height: int = 8, color: tuple[int, int, int] = (200, 120, 60)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _noise_png(size: int = 64) -> bytes:
    """A PNG that does not compress, so its byte size is predictable and large."""

    buffer = io.BytesIO()
    Image.frombytes("RGB", (size, size), os.urandom(size * size * 3)).save(buffer, format="PNG")
    return buffer.getvalue()


def _jpeg(width: int = 8, height: int = 8) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 90, 180)).save(buffer, format="JPEG")
    return buffer.getvalue()


class _ExplodingProvider:
    """Fails the test if anything actually asks it to generate."""

    provider_name = "demo"
    model_name = "demo-image-v1"

    async def generate(self, *, request: ImageGenerationRequest) -> GeneratedImage:
        raise AssertionError("no debía llamarse al proveedor")


class _CapturingProvider:
    """Records what crossed the provider boundary and returns a fixed result."""

    provider_name = "demo"
    model_name = "demo-image-v1"

    def __init__(self, *, content: bytes | None = None, mime_type: str = "image/png") -> None:
        self.requests: list[ImageGenerationRequest] = []
        self._content = content if content is not None else _png()
        self._mime_type = mime_type

    async def generate(self, *, request: ImageGenerationRequest) -> GeneratedImage:
        self.requests.append(request)
        return GeneratedImage(
            content=self._content,
            mime_type=self._mime_type,
            provider_name=self.provider_name,
            model=self.model_name,
            usage_metadata={"provider": self.provider_name, "model": self.model_name},
        )


def _mock_openrouter(
    handler, *, max_retries: int = 0
) -> OpenRouterImageGenerationProvider:
    return OpenRouterImageGenerationProvider(
        base_url="https://provider.test/api/v1",
        api_key=FAKE_API_KEY,
        model_name="vendor/image-model",
        timeout_seconds=5,
        max_retries=max_retries,
        retry_base_seconds=0,
        transport=httpx.MockTransport(handler),
    )


def _image_request(ratio: str = "1:1") -> ImageGenerationRequest:
    width, height = ASPECT_RATIOS[ratio]
    return ImageGenerationRequest(
        prompt="Una taza de café", aspect_ratio=ratio, width=width, height=height
    )


def _data_url(content: bytes, mime_type: str = "image/png") -> str:
    from base64 import b64encode

    return f"data:{mime_type};base64,{b64encode(content).decode('ascii')}"


def _approval(
    *,
    brief: dict | None = None,
    aspect_ratio: str = "1:1",
    reference_asset_id: str | None = None,
    workspace_id: str = WORKSPACE_ID,
    now: datetime | None = None,
) -> str:
    """Mint a genuine approval without going through ``/preflight``.

    Used to prove that the gates after the approval still hold on their own: a
    client that somehow holds a valid token must still be stopped by the
    capability, the provider configuration and the budget.
    """

    normalized = normalize_brief(brief or BRIEF)
    return sign_preflight(
        workspace_id=workspace_id,
        request_hash=request_fingerprint(
            prompt=compose_prompt(normalized, aspect_ratio=aspect_ratio),
            negative_prompt=compose_negative_prompt(normalized),
            aspect_ratio=aspect_ratio,
            reference_asset_id=reference_asset_id,
        ),
        now=now,
    ).token


async def _business(business_id: str = "biz_image_001") -> str:
    async with _TestingSessionFactory() as db:
        db.add(
            Business(
                id=business_id,
                workspace_id=WORKSPACE_ID,
                name="Café HiTrendy",
                category="gastronomy",
                country="HN",
                city="Tegucigalpa",
                primary_product="Café frío artesanal",
                target_audience="Clientes locales",
                preferred_platforms='["instagram"]',
                primary_objective="sales",
            )
        )
        await db.commit()
    return business_id


async def _ensure_workspace(workspace_id: str) -> None:
    """The ``client`` fixture wipes workspaces, so a neighbour is created here."""

    async with _TestingSessionFactory() as db:
        if await db.get(Workspace, workspace_id) is None:
            db.add(Workspace(id=workspace_id, name="Otro workspace"))
            await db.commit()


async def _stored_asset(
    *,
    asset_id: str,
    workspace_id: str = WORKSPACE_ID,
    content: bytes | None = None,
    mime_type: str = "image/png",
    asset_type: str = "image",
) -> str:
    await _ensure_workspace(workspace_id)
    payload = content if content is not None else _png()
    key = f"workspaces/{workspace_id}/uploads/{asset_id}.png"
    await get_object_storage_provider().put(key=key, content=payload, content_type=mime_type)
    async with _TestingSessionFactory() as db:
        db.add(
            Asset(
                id=asset_id,
                workspace_id=workspace_id,
                original_name=f"{asset_id}.png",
                storage_path=key,
                mime_type=mime_type,
                file_size_bytes=len(payload),
                asset_type=asset_type,
                width=8,
                height=8,
            )
        )
        await db.commit()
    return asset_id


async def _create_job(
    client: AsyncClient,
    *,
    key: str,
    brief: dict | None = None,
    aspect_ratio: str = "1:1",
    reference_asset_id: str | None = None,
    approval_token: str | None = None,
    confirmed: bool = True,
    project_id: str | None = None,
) -> httpx.Response:
    payload = {
        "brief": brief or BRIEF,
        "aspect_ratio": aspect_ratio,
        "reference_asset_id": reference_asset_id,
        "approval_token": approval_token
        or _approval(
            brief=brief, aspect_ratio=aspect_ratio, reference_asset_id=reference_asset_id
        ),
        "confirmed": confirmed,
        "project_id": project_id,
    }
    return await client.post(
        f"{API}/jobs", headers={**HEADERS, "Idempotency-Key": key}, json=payload
    )


async def _run_worker(*, user_id: str | None = None) -> ImageGenerationJob | None:
    """Claim and execute exactly one job, as the standalone worker would."""

    async with _TestingSessionFactory() as db:
        job = await image_service.claim_next_job(db)
        if job is None:
            return None
        return await image_service.execute_job(db, job, user_id=user_id)


async def _budget_row() -> ImageGenerationBudget | None:
    async with _TestingSessionFactory() as db:
        return await db.scalar(
            select(ImageGenerationBudget).where(
                ImageGenerationBudget.workspace_id == WORKSPACE_ID
            )
        )


async def _consumed() -> int:
    row = await _budget_row()
    return row.consumed if row else 0


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
        ):
            await db.execute(delete(model))
        await db.commit()


# --- 1..5 · las puertas previas a cualquier gasto ---------------------------


@pytest.mark.asyncio
async def test_disabled_capability_blocks_preflight_and_creation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """1. Capability disabled."""

    monkeypatch.setattr(settings, "image_generation_enabled", False)
    monkeypatch.setattr(image_service, "get_image_generation_provider", _ExplodingProvider)

    preflight = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "1:1"}
    )
    assert preflight.status_code == 200
    body = preflight.json()
    assert body["allowed"] is False
    assert body["reason_code"] == CapabilityStatus.DISABLED.value
    assert body["approval_token"] is None
    assert body["capability"]["status"] == CapabilityStatus.DISABLED.value

    # Even holding a genuine approval, creation is refused and nothing is spent.
    created = await _create_job(client, key="key-disabled")
    assert created.status_code == 503
    assert created.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert await _consumed() == 0
    async with _TestingSessionFactory() as db:
        assert await db.scalar(select(ImageGenerationJob)) is None


@pytest.mark.asyncio
async def test_unconfigured_provider_never_approves_a_generation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2. Provider unconfigured."""

    monkeypatch.setattr(settings, "image_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    monkeypatch.setattr(settings, "image_generation_model", "vendor/image-model")
    monkeypatch.setattr(settings, "image_generation_allowed_models", ("vendor/image-model",))

    assert settings.image_generation_configured is False
    capability = get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION)
    assert capability.status is CapabilityStatus.UNCONFIGURED

    preflight = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "1:1"}
    )
    body = preflight.json()
    assert body["allowed"] is False
    assert body["reason_code"] == CapabilityStatus.UNCONFIGURED.value
    assert body["approval_token"] is None

    created = await _create_job(client, key="key-unconfigured")
    assert created.status_code == 503
    assert created.json()["error"]["code"] == "CAPABILITY_UNAVAILABLE"
    assert await _consumed() == 0
    with pytest.raises(AppError) as excinfo:
        get_image_generation_provider()
    assert excinfo.value.code == "IMAGE_PROVIDER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_model_outside_the_operator_allowlist_disables_paid_generation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """3. Paid generation disabled: the allow-list is the operator kill-switch."""

    monkeypatch.setattr(settings, "image_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", FAKE_API_KEY)
    monkeypatch.setattr(settings, "image_generation_model", "vendor/image-model")
    monkeypatch.setattr(settings, "image_generation_allowed_models", ())

    assert settings.image_generation_configured is False
    assert (
        get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION).status
        is CapabilityStatus.UNCONFIGURED
    )
    with pytest.raises(AppError) as excinfo:
        get_image_generation_provider()
    assert excinfo.value.code == "IMAGE_PROVIDER_UNAVAILABLE"
    assert FAKE_API_KEY not in excinfo.value.message

    created = await _create_job(client, key="key-not-allowed")
    assert created.status_code == 503
    assert await _consumed() == 0


@pytest.mark.asyncio
async def test_preflight_never_reaches_a_provider(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4. Preflight no llama al proveedor."""

    monkeypatch.setattr(image_service, "get_image_generation_provider", _ExplodingProvider)

    response = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "4:5"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["aspect_ratio"] == "4:5"
    assert body["approval_token"]
    assert body["prompt_preview"].startswith("Imagen para redes sociales en formato 4:5.")
    # The estimate is visible before anything is spent.
    assert body["budget"]["remaining"] == settings.image_generation_daily_budget
    assert await _consumed() == 0
    async with _TestingSessionFactory() as db:
        assert await db.scalar(select(ImageGenerationJob)) is None


@pytest.mark.asyncio
async def test_preflight_shows_what_will_be_avoided_and_signs_it(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """4b. Lo que se evita se revisa, se firma y viaja al proveedor.

    Un campo editable que se guarda y se ignora es peor que no ofrecerlo: el
    usuario cree haber puesto un límite que nunca existió.
    """

    monkeypatch.setattr(image_service, "get_image_generation_provider", _ExplodingProvider)

    brief = {**BRIEF, "avoid": "Texto ilegible"}
    response = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": brief, "aspect_ratio": "1:1"}
    )
    assert response.status_code == 200
    body = response.json()
    # Se muestra aparte porque está redactado como exclusión, no como escena.
    assert body["negative_prompt_preview"] == "Texto ilegible"
    assert "Texto ilegible" not in body["prompt_preview"]

    # Y la firma lo cubre: cambiarlo invalida la aprobación.
    token = body["approval_token"]
    tampered = await client.post(
        f"{API}/jobs",
        headers={**HEADERS, "Idempotency-Key": "key-avoid-tampered"},
        json={
            "brief": {**brief, "avoid": "Nada"},
            "aspect_ratio": "1:1",
            "reference_asset_id": None,
            "approval_token": token,
            "confirmed": True,
        },
    )
    assert tampered.status_code == 409
    assert tampered.json()["error"]["code"] == "IMAGE_PREFLIGHT_REQUIRED"
    assert await _consumed() == 0


@pytest.mark.asyncio
async def test_the_negative_prompt_reaches_the_provider_payload() -> None:
    """4c. La restricción aprobada llega al cuerpo que sale hacia el modelo."""

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"images": [{"image_url": {"url": _data_url(_png())}}]}}
                ]
            },
        )

    width, height = ASPECT_RATIOS["1:1"]
    await _mock_openrouter(handler).generate(
        request=ImageGenerationRequest(
            prompt="Una taza de café",
            aspect_ratio="1:1",
            width=width,
            height=height,
            negative_prompt="Manos borrosas",
        )
    )
    payload = json.loads(str(captured["body"]))
    # El esquema del cuerpo no cambia: la restricción viaja como una parte más.
    assert set(payload) == {"model", "modalities", "messages", "extra_body"}
    parts = payload["messages"][0]["content"]
    assert any(
        part.get("type") == "text" and "Manos borrosas" in part.get("text", "")
        for part in parts
    )


@pytest.mark.asyncio
async def test_a_lowered_limit_never_shows_credit_that_will_be_refused(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """8. El presupuesto efectivo es el menor entre lo guardado y lo configurado.

    Bajar el límite a media jornada no puede dejar al usuario mirando crédito
    que el servidor va a rechazar en cuanto lo intente gastar.
    """

    provider = _ExplodingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    # La fila del día se crea con el límite alto vigente en ese momento.
    first = await _create_job(client, key="key-effective-1")
    assert first.status_code == 202
    assert await _consumed() == 1

    # El operador baja el límite del día en curso.
    monkeypatch.setattr(settings, "image_generation_daily_budget", 1)

    preflight = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "1:1"}
    )
    body = preflight.json()
    assert body["budget"]["total"] == 1
    assert body["budget"]["remaining"] == 0
    assert body["allowed"] is False
    assert body["approval_token"] is None

    # Y el rechazo del servidor coincide con lo que acaba de reportar.
    refused = await _create_job(client, key="key-effective-2")
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "IMAGE_QUOTA_EXHAUSTED"

    # Con un límite por debajo de lo ya gastado, se informa agotado, no negativo.
    monkeypatch.setattr(settings, "image_generation_daily_budget", 0)
    drained = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "1:1"}
    )
    assert drained.json()["budget"] == {
        **drained.json()["budget"],
        "total": 0,
        "remaining": 0,
    }


@pytest.mark.asyncio
async def test_exhausted_budget_blocks_before_any_provider_call(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """5. Budget insuficiente bloquea antes del proveedor."""

    monkeypatch.setattr(settings, "image_generation_daily_budget", 1)
    provider = _ExplodingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    first = await _create_job(client, key="key-budget-1")
    assert first.status_code == 202
    assert await _consumed() == 1

    preflight = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "1:1"}
    )
    body = preflight.json()
    assert body["allowed"] is False
    assert body["reason_code"] == CapabilityStatus.QUOTA_EXHAUSTED.value
    assert body["budget"]["remaining"] == 0
    assert body["approval_token"] is None

    second = await _create_job(client, key="key-budget-2")
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "IMAGE_QUOTA_EXHAUSTED"
    # Still exactly one reservation: the refused request spent nothing.
    assert await _consumed() == 1


# --- 6..12 · el contrato del proveedor --------------------------------------


@pytest.mark.asyncio
async def test_provider_maps_payment_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """6. ``402`` de OpenRouter."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(handler).generate(request=_image_request())
    error = excinfo.value
    assert error.code == "PAYMENT_REQUIRED"
    assert error.status_code == 402
    assert error.retryable is False
    # Neither the balance nor the upstream sentence reaches the user.
    assert "Insufficient credits" not in error.message
    assert FAKE_API_KEY not in error.message


@pytest.mark.asyncio
async def test_provider_maps_rate_limit_with_and_without_retry_after() -> None:
    """7. ``429``."""

    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "30"}, json={})

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(limited).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_RATE_LIMITED"
    assert excinfo.value.status_code == 429
    assert excinfo.value.retryable is True
    assert excinfo.value.retry_after == 30

    def exhausted(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(exhausted).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_QUOTA_EXHAUSTED"
    assert excinfo.value.retryable is False

    # An absurd Retry-After is ignored rather than echoed back to a browser.
    def absurd(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "999999"}, json={})

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(absurd).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_QUOTA_EXHAUSTED"


@pytest.mark.asyncio
async def test_provider_maps_a_timeout() -> None:
    """8. Timeout."""

    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        raise httpx.TimeoutException("timeout", request=request)

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(handler).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_TIMEOUT"
    assert excinfo.value.status_code == 504
    assert excinfo.value.retryable is True
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_invalid_payloads_are_rejected_at_both_boundaries(
    client: AsyncClient,
) -> None:
    """9. Payload inválido, del cliente hacia dentro y del proveedor hacia fuera."""

    # A client payload that is not a legal request never becomes a job.
    missing_subject = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json={"brief": {**BRIEF, "subject": ""}, "aspect_ratio": "1:1"},
    )
    assert missing_subject.status_code == 422
    assert missing_subject.json()["error"]["code"] == "VALIDATION_ERROR"

    # A reference that is a URL, a path or a data URL cannot even be expressed.
    for hostile in ("https://evil.test/a.png", "../../etc/passwd", "file:///etc/passwd"):
        response = await client.post(
            f"{API}/preflight",
            headers=HEADERS,
            json={"brief": BRIEF, "aspect_ratio": "1:1", "reference_asset_id": hostile},
        )
        assert response.status_code == 422, hostile

    # A provider body that does not match the contract is not an image.
    def malformed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json at all")

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(malformed).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_INVALID_RESPONSE"

    async with _TestingSessionFactory() as db:
        assert await db.scalar(select(ImageGenerationJob)) is None


@pytest.mark.asyncio
async def test_provider_rejects_a_response_without_an_image() -> None:
    """10. Respuesta sin imagen."""

    def text_only(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": "No puedo generar eso."}}
                ]
            },
        )

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(text_only).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_INVALID_RESPONSE"
    assert excinfo.value.status_code == 502

    # A remote URL is not an image either: fetching it would be an unvalidated
    # request to an address the provider chose.
    def remote_url(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "images": [
                                {"image_url": {"url": "https://cdn.evil.test/i.png"}}
                            ]
                        }
                    }
                ]
            },
        )

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(remote_url).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_remote_image_url_is_downloaded_through_the_injected_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model-provided https URL is resolved, checked, then fetched with the
    provider's own (mockable) transport rather than a separate live client."""

    import socket as socket_module

    from app.providers import images as images_module

    def fake_getaddrinfo(host: str, port: object) -> list[tuple]:
        assert host == "cdn.example.test"
        return [(socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(images_module.socket, "getaddrinfo", fake_getaddrinfo)

    image_bytes = _png()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.example.test":
            return httpx.Response(
                200, headers={"content-type": "image/png"}, content=image_bytes
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "images": [
                                {"image_url": {"url": "https://cdn.example.test/i.png"}}
                            ]
                        }
                    }
                ]
            },
        )

    generated = await _mock_openrouter(handler).generate(request=_image_request())
    assert generated.content == image_bytes
    assert generated.mime_type == "image/png"


@pytest.mark.asyncio
async def test_remote_image_url_resolving_to_a_private_ip_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL whose host resolves to a private/loopback address must never be
    fetched, even if the model that returned it is otherwise trusted."""

    import socket as socket_module

    from app.providers import images as images_module

    def fake_getaddrinfo(host: str, port: object) -> list[tuple]:
        assert host == "internal.example.test"
        return [(socket_module.AF_INET, socket_module.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(images_module.socket, "getaddrinfo", fake_getaddrinfo)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "images": [
                                {"image_url": {"url": "https://internal.example.test/i.png"}}
                            ]
                        }
                    }
                ]
            },
        )

    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(handler).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_oversized_images_are_refused_before_decoding_and_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """11. Imagen demasiado grande."""

    monkeypatch.setattr(settings, "image_generation_max_bytes", 512)

    def huge(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "images": [
                                {"image_url": {"url": _data_url(_noise_png(64))}}
                            ]
                        }
                    }
                ]
            },
        )

    # The base64 is measured before it is decoded, so a huge body never becomes
    # a huge allocation.
    with pytest.raises(AppError) as excinfo:
        await _mock_openrouter(huge).generate(request=_image_request())
    assert excinfo.value.code == "IMAGE_PROVIDER_INVALID_RESPONSE"

    # And the ceiling is enforced again on the decoded bytes.
    with pytest.raises(AppError) as excinfo:
        validate_image_bytes(
            _noise_png(64),
            "image/png",
            max_bytes=512,
            size_message="La imagen generada supera el tamaño permitido.",
        )
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert "supera el tamaño permitido" in excinfo.value.message


def test_a_lied_about_mime_type_is_rejected() -> None:
    """12. MIME falso."""

    with pytest.raises(AppError) as excinfo:
        validate_image_bytes(_jpeg(), "image/png")
    assert excinfo.value.code == "VALIDATION_ERROR"

    with pytest.raises(AppError):
        validate_image_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/png")

    with pytest.raises(AppError):
        validate_image_bytes(_png(), "image/svg+xml")

    # The honest pairing still works.
    assert validate_image_bytes(_png(), "image/png").mime_type == "image/png"


# --- 13..16 · exactamente tres formatos -------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("ratio", ["1:1", "4:5", "9:16"])
async def test_each_supported_ratio_stores_those_exact_dimensions(
    client: AsyncClient, ratio: str
) -> None:
    """13, 14 y 15. Ratios 1:1, 4:5 y 9:16."""

    preflight = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": ratio}
    )
    assert preflight.status_code == 200
    approved = preflight.json()
    assert approved["allowed"] is True
    assert approved["aspect_ratio"] == ratio

    created = await _create_job(
        client, key=f"key-ratio-{ratio}", aspect_ratio=ratio, approval_token=approved["approval_token"]
    )
    assert created.status_code == 202
    assert created.json()["aspect_ratio"] == ratio

    job = await _run_worker()
    assert job is not None
    assert job.status == "succeeded"
    assert job.asset_id

    async with _TestingSessionFactory() as db:
        asset = await db.get(Asset, job.asset_id)
    assert asset is not None
    assert (asset.width, asset.height) == ASPECT_RATIOS[ratio]
    assert asset.asset_type == "image"


@pytest.mark.asyncio
async def test_an_arbitrary_ratio_is_rejected(client: AsyncClient) -> None:
    """16. Ratio arbitrario rechazado."""

    # Ratios the domain rejects: they fit the field but are not one of the three.
    for ratio in ("3:2", "16:9", "1:2", ""):
        preflight = await client.post(
            f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": ratio}
        )
        assert preflight.status_code == 422, ratio
        assert preflight.json()["error"]["code"] == "VALIDATION_ERROR", ratio

    # A ratio longer than the field never reaches the domain at all.
    oversized = await client.post(
        f"{API}/preflight", headers=HEADERS, json={"brief": BRIEF, "aspect_ratio": "1024x1024"}
    )
    assert oversized.status_code == 422

    created = await _create_job(client, key="key-bad-ratio", aspect_ratio="16:9")
    assert created.status_code == 422
    assert await _consumed() == 0
    assert set(ASPECT_RATIOS) == {"1:1", "4:5", "9:16"}


# --- 17..19 · referencias ----------------------------------------------------


@pytest.mark.asyncio
async def test_a_reference_owned_by_the_workspace_reaches_the_provider(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """17. Referencia válida."""

    reference_bytes = _png(color=(20, 160, 90))
    asset_id = await _stored_asset(asset_id="ast_reference_ok", content=reference_bytes)
    provider = _CapturingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    preflight = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json={"brief": BRIEF, "aspect_ratio": "1:1", "reference_asset_id": asset_id},
    )
    assert preflight.status_code == 200
    approved = preflight.json()
    assert approved["allowed"] is True
    assert approved["reference_asset_id"] == asset_id

    created = await _create_job(
        client,
        key="key-reference-ok",
        reference_asset_id=asset_id,
        approval_token=approved["approval_token"],
    )
    assert created.status_code == 202
    assert created.json()["reference_asset_id"] == asset_id

    job = await _run_worker()
    assert job is not None and job.status == "succeeded"
    assert len(provider.requests) == 1
    sent = provider.requests[0]
    assert sent.reference_image == reference_bytes
    assert sent.reference_mime_type == "image/png"
    # The reference travels as bytes; its identity does not.
    assert asset_id not in sent.prompt
    assert WORKSPACE_ID not in sent.prompt


@pytest.mark.asyncio
async def test_a_reference_from_another_workspace_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """18. Referencia ajena rechazada."""

    monkeypatch.setattr(image_service, "get_image_generation_provider", _ExplodingProvider)
    foreign = await _stored_asset(
        asset_id="ast_reference_foreign", workspace_id=OTHER_WORKSPACE_ID
    )

    preflight = await client.post(
        f"{API}/preflight",
        headers=HEADERS,
        json={"brief": BRIEF, "aspect_ratio": "1:1", "reference_asset_id": foreign},
    )
    assert preflight.status_code == 404
    assert preflight.json()["error"]["code"] == "NOT_FOUND"

    created = await _create_job(
        client, key="key-reference-foreign", reference_asset_id=foreign
    )
    assert created.status_code == 404
    assert await _consumed() == 0

    missing = await _create_job(
        client, key="key-reference-missing", reference_asset_id="ast_does_not_exist"
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_an_oversized_reference_fails_before_the_provider_and_refunds(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """19. Referencia demasiado grande."""

    asset_id = await _stored_asset(asset_id="ast_reference_big", content=_noise_png(64))
    provider = _ExplodingProvider()
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    created = await _create_job(
        client, key="key-reference-big", reference_asset_id=asset_id
    )
    assert created.status_code == 202
    assert await _consumed() == 1

    # The ceiling drops after the job was accepted: the worker is the one that
    # must refuse it, and it must do so before spending anything.
    monkeypatch.setattr(settings, "image_generation_max_bytes", 512)
    job = await _run_worker()
    assert job is not None
    assert job.status == "failed"
    assert job.asset_id is None
    assert "referencia" in (job.last_error or "").lower()
    # Nothing was generated, so the reservation goes back.
    assert await _consumed() == 0


# --- 29..32 · lo que nunca sale del servidor --------------------------------


@pytest.mark.asyncio
async def test_a_signed_link_only_serves_its_own_workspace(client: AsyncClient) -> None:
    """29. Signed URL requiere workspace autorizado."""

    content = _png(color=(90, 30, 140))
    asset_id = await _stored_asset(asset_id="ast_signed_ok", content=content)
    signed = sign_image_url(asset_id=asset_id, workspace_id=WORKSPACE_ID)

    ok = await client.get(signed.url)
    assert ok.status_code == 200
    assert ok.content == content
    assert ok.headers["content-type"].startswith("image/png")
    assert ok.headers["cache-control"] == "private, no-store"

    # Re-pointing a valid signature at another workspace breaks it.
    tampered = signed.url.replace(f"workspace={WORKSPACE_ID}", f"workspace={OTHER_WORKSPACE_ID}")
    assert (await client.get(tampered)).status_code == 403

    # A signature minted for another workspace does not open this asset either.
    foreign = sign_image_url(asset_id=asset_id, workspace_id=OTHER_WORKSPACE_ID)
    assert (await client.get(foreign.url)).status_code == 403

    # And an unsigned request is refused like a forged one.
    bare = await client.get(f"{API}/files/{asset_id}")
    assert bare.status_code == 403
    assert bare.json()["error"]["code"] == "IMAGE_LINK_INVALID"


@pytest.mark.asyncio
async def test_a_signed_link_expires(client: AsyncClient) -> None:
    """30. Signed URL expira."""

    asset_id = await _stored_asset(asset_id="ast_signed_expired")
    expired = sign_image_url(
        asset_id=asset_id,
        workspace_id=WORKSPACE_ID,
        now=datetime.now(UTC) - timedelta(seconds=settings.image_signed_url_ttl_seconds + 60),
    )
    assert expired.expires_at < datetime.now(UTC)

    response = await client.get(expired.url)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "IMAGE_LINK_INVALID"

    # Extending the expiry by hand invalidates the signature.
    stretched = sign_image_url(asset_id=asset_id, workspace_id=WORKSPACE_ID)
    expires = stretched.url.split("expires=")[1].split("&")[0]
    forged = stretched.url.replace(f"expires={expires}", f"expires={int(expires) + 86_400}")
    assert (await client.get(forged)).status_code == 403


@pytest.mark.asyncio
async def test_no_base64_or_signed_link_is_ever_persisted(client: AsyncClient) -> None:
    """31. Asset no es base64 en DB."""

    from base64 import b64encode

    created = await _create_job(client, key="key-no-base64")
    assert created.status_code == 202
    job_id = created.json()["id"]
    # The creation response is what an idempotency replay stores: no link here.
    assert "image_url" not in created.json()

    job = await _run_worker()
    assert job is not None and job.status == "succeeded"

    async with _TestingSessionFactory() as db:
        asset = await db.get(Asset, job.asset_id)
        record = await db.scalar(
            select(IdempotencyRecord).where(IdempotencyRecord.key == "key-no-base64")
        )
    assert asset is not None
    content = await get_object_storage_provider().read(key=asset.storage_path)
    encoded = b64encode(content).decode("ascii")

    stored_text = " ".join(
        str(value)
        for value in (
            *(getattr(asset, column) for column in ("storage_path", "original_name", "mime_type")),
            *(getattr(job, column) for column in ("prompt", "last_error", "provider", "model")),
        )
        if value is not None
    )
    assert encoded[:64] not in stored_text
    assert "base64" not in stored_text
    assert asset.storage_path == f"workspaces/{WORKSPACE_ID}/generated/{job_id}.png"
    assert asset.file_size_bytes == len(content)

    # The persisted idempotency replay carries no link and no base64 either.
    assert record is not None
    replay = json.loads(record.response_json)
    assert "image_url" not in replay
    assert encoded[:64] not in (record.response_json or "")

    # Only a read mints a link, and it is temporary.
    read = await client.get(f"{API}/jobs/{job_id}", headers=HEADERS)
    assert read.status_code == 200
    body = read.json()
    assert body["image_url"].startswith(f"{settings.api_prefix}/images/files/")
    assert body["image_expires_at"]
    first_url = body["image_url"]
    second = await client.get(f"{API}/jobs/{job_id}", headers=HEADERS)
    assert second.json()["image_url"].startswith(f"{settings.api_prefix}/images/files/")
    assert "signature=" in first_url


@pytest.mark.asyncio
async def test_provider_secrets_never_reach_responses_or_logs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """32. Secrets no aparecen en respuestas ni logs."""

    def refuses(request: httpx.Request) -> httpx.Response:
        # The upstream body deliberately echoes everything we must not surface.
        return httpx.Response(
            402,
            json={
                "error": {
                    "message": "Insufficient credits: balance 0.12 USD",
                    "authorization": request.headers.get("authorization"),
                }
            },
        )

    provider = _mock_openrouter(refuses)
    monkeypatch.setattr(image_service, "get_image_generation_provider", lambda **_: provider)

    created = await _create_job(client, key="key-secrets")
    assert created.status_code == 202
    job_id = created.json()["id"]

    with caplog.at_level(logging.DEBUG):
        job = await _run_worker()
    assert job is not None and job.status == "failed"

    read = await client.get(f"{API}/jobs/{job_id}", headers=HEADERS)
    assert read.status_code == 200
    body = read.json()
    serialized = json.dumps(body, ensure_ascii=False)

    for secret in (FAKE_API_KEY, "Bearer", "Insufficient credits", "0.12 USD", "authorization"):
        assert secret not in serialized, secret
        assert secret not in caplog.text, secret
    # The user gets one short, actionable Spanish sentence.
    assert body["error_code"] == "PAYMENT_REQUIRED"
    assert body["error"] == "Esta generación de imágenes requiere presupuesto habilitado."
    # The prompt is not part of the job contract either.
    assert "prompt" not in body
    assert "provider" not in body
    assert "model" not in body
    # A billing refusal degrades the capability transiently, never permanently.
    assert (
        get_runtime_capability_registry().get_capability(Capability.IMAGE_GENERATION).status
        is CapabilityStatus.PAYMENT_REQUIRED
    )


@pytest.mark.asyncio
async def test_the_request_that_leaves_carries_no_tenant_data() -> None:
    """32 (continuación). Nada del workspace cruza el límite del proveedor."""

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"images": [{"image_url": {"url": _data_url(_png())}}]}}
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 0, "total_tokens": 12},
            },
        )

    generated = await _mock_openrouter(handler).generate(request=_image_request())
    body = str(captured["body"])
    for forbidden in (WORKSPACE_ID, "ws_", "usr_", "@example.com", "biz_"):
        assert forbidden not in body, forbidden
    payload = json.loads(body)
    assert set(payload) == {"model", "modalities", "messages", "extra_body"}
    assert payload["model"] == "vendor/image-model"

    # Only counters survive from the provider response.
    assert set(generated.usage_metadata) == {
        "provider",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
    }


# --- 35, 36 · fallback y ausencia de llamadas reales ------------------------


@pytest.mark.asyncio
async def test_the_visual_brief_works_without_any_generation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """35. Visual brief funciona sin generación."""

    monkeypatch.setattr(settings, "image_generation_enabled", False)
    monkeypatch.setattr(image_service, "get_image_generation_provider", _ExplodingProvider)
    business_id = await _business()

    response = await client.post(
        f"{API}/brief",
        headers=HEADERS,
        json={
            "business_id": business_id,
            "publication_text": "Hoy estrenamos nuestro café frío de temporada.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["brief"]["subject"]
    assert body["brief"]["setting"]
    assert body["brief"]["avoid"]
    assert body["aspect_ratios"] == ["1:1", "4:5", "9:16"]
    assert body["capability"]["status"] == CapabilityStatus.DISABLED.value
    # The documented fallback is named, so the UI can show it honestly.
    assert body["capability"]["fallback"]
    assert await _consumed() == 0

    # A brief for a business of another workspace is not readable.
    await _ensure_workspace(OTHER_WORKSPACE_ID)
    async with _TestingSessionFactory() as db:
        db.add(
            Business(
                id="biz_foreign_001",
                workspace_id=OTHER_WORKSPACE_ID,
                name="Ajeno",
                category="gastronomy",
                country="HN",
                city="Tegucigalpa",
                primary_product="Café",
                target_audience="Clientes",
                preferred_platforms='["instagram"]',
                primary_objective="sales",
            )
        )
        await db.commit()
    foreign = await client.post(
        f"{API}/brief", headers=HEADERS, json={"business_id": "biz_foreign_001"}
    )
    assert foreign.status_code == 404


def test_no_real_image_calls_can_happen_in_ci() -> None:
    """36. No existen llamadas reales en CI."""

    assert settings.run_real_images_smoke is False

    root = Path(__file__).resolve().parents[3]
    backend = Path(__file__).resolve().parents[1]

    pyproject = (backend / "pyproject.toml").read_text(encoding="utf-8")
    assert "real_images: smoke opt-in" in pyproject

    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "not real_images" in workflow
    assert "RUN_REAL_IMAGES_SMOKE: 1" not in workflow
    assert "RUN_REAL_IMAGES_SMOKE=1" not in workflow

    source = (backend / "tests/test_real_images_smoke.py").read_text(encoding="utf-8")
    assert "@pytest.mark.real_images" in source
    assert "RUN_REAL_IMAGES_SMOKE" in source
    assert "pytestmark = pytest.mark.skipif" in source

    # No test in this suite may hold a real endpoint. The needle is assembled at
    # runtime so this assertion does not match its own source line.
    needle = "openrouter" + ".ai"
    for path in sorted((backend / "tests").glob("test_image*.py")):
        body = path.read_text(encoding="utf-8")
        assert needle not in body, path.name
