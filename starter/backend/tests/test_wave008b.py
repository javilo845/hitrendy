from __future__ import annotations

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, func, select

from app.conversations.models import AIUsageEvent, GeneratedArtifact, IdempotencyRecord
from app.core.errors import AppError
from app.dependencies import get_db
from app.main import app

WORKSPACE_ID = "ws_test_001"


class UsageProvider:
    provider_name = "openrouter"
    model_name = "openrouter/free"

    def __init__(self, failure: AppError | None = None) -> None:
        self.calls = 0
        self.failure = failure

    async def generate_advice(self, *, request: object) -> dict:
        self.calls += 1
        if self.failure:
            raise self.failure
        return {
            "summary": "Recomendación artesanal para el negocio.",
            "recommendations": [
                {"title": "Acción clara", "description": "Destaca el café artesanal.", "priority": "high"}
            ],
            "next_actions": ["Publica un caption accionable."],
            "__provider_metadata": self._metadata(),
        }

    async def generate_social_post(self, *, request: object) -> dict:
        self.calls += 1
        if self.failure:
            raise self.failure
        return {
            "artifact_type": "social_post",
            "platform": "instagram",
            "hook": "Café artesanal para tu día",
            "caption": "Conoce nuestro café artesanal para jóvenes profesionales.",
            "call_to_action": "Escríbenos hoy.",
            "hashtags": ["#CafeArtesanal"],
            "visual_direction": "Producto claro con luz natural.",
            "format_recommendation": "reel",
            "assumptions": ["Se usó el contexto de marca."],
            "__provider_metadata": self._metadata(),
        }

    async def generate_short_video_script(self, *, request: object) -> dict:
        self.calls += 1
        if self.failure:
            raise self.failure
        return {
            "artifact_type": "short_video_script",
            "platform": "instagram",
            "hook": "Café artesanal en segundos",
            "duration_seconds": 20,
            "scenes": [
                {
                    "order": 1,
                    "duration_seconds": 10,
                    "visual": "Primer plano del café.",
                    "on_screen_text": "Café artesanal",
                    "voiceover": "Conoce una pausa diferente.",
                },
                {
                    "order": 2,
                    "duration_seconds": 10,
                    "visual": "Cierre con el negocio.",
                    "on_screen_text": "Conócelo hoy",
                    "voiceover": "Escríbenos hoy.",
                },
            ],
            "call_to_action": "Escríbenos hoy.",
            "caption": "Café artesanal para tu día.",
            "assumptions": ["Se usó el contexto de marca."],
            "__provider_metadata": self._metadata(),
        }

    @staticmethod
    def _metadata() -> dict[str, object]:
        return {
            "requested_model": "openrouter/free",
            "actual_model": "provider/physical-model",
            "prompt_tokens": 11,
            "completion_tokens": 13,
            "total_tokens": 24,
            "reported_cost": "0.00001234",
            "currency": "USD",
            "provider_request_id": "req-wave-008b",
        }


class FailOnceProvider(UsageProvider):
    def __init__(self) -> None:
        super().__init__()
        self._failed = False

    async def generate_advice(self, *, request: object) -> dict:
        self.calls += 1
        if not self._failed:
            self._failed = True
            raise AppError("GENERATION_PROVIDER_UNAVAILABLE", "provider unavailable", status_code=503)
        return {
            "summary": "Recomendación lista.",
            "recommendations": [
                {"title": "Acción clara", "description": "Destaca el café artesanal.", "priority": "high"}
            ],
            "next_actions": ["Publica hoy."],
            "__provider_metadata": self._metadata(),
        }

    async def generate_social_post(self, *, request: object) -> dict:
        self.calls += 1
        if not self._failed:
            self._failed = True
            raise AppError("GENERATION_PROVIDER_UNAVAILABLE", "provider unavailable", status_code=503)
        payload = await UsageProvider.generate_social_post(self, request=request)
        self.calls -= 1
        return payload


class RepairUsageProvider(UsageProvider):
    async def generate_social_post(self, *, request: object) -> dict:
        self.calls += 1
        payload = await UsageProvider.generate_social_post(self, request=request)
        self.calls -= 1
        payload["caption"] = "Café barato para todos."
        payload["__provider_metadata"] = {
            **self._metadata(),
            "prompt_tokens": 3,
            "completion_tokens": 5,
            "total_tokens": 8,
            "reported_cost": "0.001",
            "provider_request_id": "repair-first",
        }
        return payload

    async def repair_social_post(
        self, *, request: object, invalid_output: dict, errors: list[str]
    ) -> dict:
        self.calls += 1
        payload = await UsageProvider.generate_social_post(self, request=request)
        self.calls -= 1
        payload["__provider_metadata"] = {
            **self._metadata(),
            "actual_model": "provider/final-model",
            "prompt_tokens": 7,
            "completion_tokens": 11,
            "total_tokens": 18,
            "reported_cost": "0.002",
            "provider_request_id": "repair-second",
        }
        return payload


async def _business(client: AsyncClient) -> str:
    created = await client.post(
        "/api/v1/businesses",
        headers={"X-Workspace-Id": WORKSPACE_ID},
        json={
            "name": "Café Wave", "category": "gastronomy", "country": "Honduras",
            "city": "Tegucigalpa", "primary_product": "café artesanal",
            "target_audience": "jóvenes profesionales", "preferred_platforms": ["instagram"],
            "primary_objective": "engagement",
        },
    )
    assert created.status_code == 201, created.text
    business_id = created.json()["id"]
    brand = await client.put(
        f"/api/v1/businesses/{business_id}/brand-profile",
        headers={"X-Workspace-Id": WORKSPACE_ID},
        json={
            "voice_tones": ["friendly"], "value_proposition": "Café preparado al momento.",
            "preferred_words": ["artesanal"], "forbidden_words": ["barato"],
        },
    )
    assert brand.status_code == 200
    return business_id


async def _usage() -> list[AIUsageEvent]:
    async with _test_db() as session:
        result = await session.execute(select(AIUsageEvent).order_by(AIUsageEvent.created_at.desc()))
        return list(result.scalars())


async def _idempotency_status(endpoint: str, key: str) -> str | None:
    async with _test_db() as session:
        result = await session.execute(
            select(IdempotencyRecord.status).where(
                IdempotencyRecord.workspace_id == WORKSPACE_ID,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.key == key,
            )
        )
        return result.scalar_one_or_none()


@asynccontextmanager
async def _test_db():
    provider = app.dependency_overrides[get_db]()
    session = await anext(provider)
    try:
        yield session
    finally:
        await provider.aclose()


@pytest_asyncio.fixture(autouse=True)
async def clear_usage_events(client: AsyncClient) -> None:
    del client
    async with _test_db() as session:
        await session.execute(delete(AIUsageEvent))
        await session.commit()


@pytest.mark.asyncio
async def test_advisor_is_structured_idempotent_and_records_complete_usage(client, monkeypatch) -> None:
    provider = UsageProvider()
    monkeypatch.setattr("app.business.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "advisor-wave-key"}
    payload = {"text": "Dame una recomendación", "quality_level": "fast", "locale": "es"}
    first = await client.post(f"/api/v1/businesses/{business_id}/advisor", headers=headers, json=payload)
    replay = await client.post(f"/api/v1/businesses/{business_id}/advisor", headers=headers, json=payload)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert set(first.json()["advisor"]) == {"summary", "recommendations", "next_actions"}
    assert provider.calls == 1
    usage = await _usage()
    event = usage[0]
    assert len(usage) == 1
    assert event.requested_model == "openrouter/free"
    assert event.actual_model == "provider/physical-model"
    assert event.prompt_tokens == 11 and event.total_tokens == 24
    assert event.reported_cost == Decimal("0.00001234")
    assert event.provider_request_id == "req-wave-008b"
    assert event.outcome == "success"


@pytest.mark.asyncio
async def test_copywriter_records_one_artifact_and_one_usage_on_idempotency_replay(client, monkeypatch) -> None:
    provider = UsageProvider()
    monkeypatch.setattr("app.conversations.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    conversation = await client.post(
        "/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID},
        json={"business_id": business_id, "title": "Wave copywriter"},
    )
    conversation_id = conversation.json()["id"]
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "copywriter-wave-key"}
    payload = {"text": "Crea un caption", "quality_level": "fast", "locale": "pt"}
    first = await client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers, json=payload)
    replay = await client.post(f"/api/v1/conversations/{conversation_id}/messages", headers=headers, json=payload)

    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert provider.calls == 1
    usage = await _usage()
    assert len(usage) == 1 and usage[0].capability == "copywriter"
    async with _test_db() as session:
        artifact_count = await session.scalar(
            select(func.count()).select_from(GeneratedArtifact).where(
                GeneratedArtifact.conversation_id == conversation_id
            )
        )
    assert artifact_count == 1


@pytest.mark.asyncio
async def test_copywriter_repair_records_combined_usage_once(client, monkeypatch) -> None:
    provider = RepairUsageProvider()
    monkeypatch.setattr("app.conversations.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    conversation = await client.post(
        "/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID},
        json={"business_id": business_id, "title": "Repair usage"},
    )
    conversation_id = conversation.json()["id"]

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers={"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "repair-usage-key"},
        json={"text": "Crea un caption"},
    )

    assert response.status_code == 200
    assert provider.calls == 2
    usage = await _usage()
    assert len(usage) == 1
    assert usage[0].prompt_tokens == 10
    assert usage[0].completion_tokens == 16
    assert usage[0].total_tokens == 26
    assert usage[0].reported_cost == Decimal("0.003")
    assert usage[0].actual_model == "provider/final-model"
    assert usage[0].provider_request_id == "repair-second"
    async with _test_db() as session:
        artifact_count = await session.scalar(
            select(func.count()).select_from(GeneratedArtifact).where(
                GeneratedArtifact.conversation_id == conversation_id
            )
        )
    assert artifact_count == 1


@pytest.mark.asyncio
async def test_short_video_script_records_provider_usage_metadata(client, monkeypatch) -> None:
    provider = UsageProvider()
    monkeypatch.setattr("app.conversations.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    conversation = await client.post(
        "/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID},
        json={"business_id": business_id, "title": "Video usage"},
    )

    response = await client.post(
        f"/api/v1/conversations/{conversation.json()['id']}/messages",
        headers={"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "video-usage-key"},
        json={"text": "Crea un guion", "ui_intent": "create_short_video_script"},
    )

    assert response.status_code == 200
    usage = await _usage()
    assert len(usage) == 1
    assert usage[0].requested_model == "openrouter/free"
    assert usage[0].actual_model == "provider/physical-model"
    assert usage[0].total_tokens == 24
    assert usage[0].reported_cost == Decimal("0.00001234")
    assert usage[0].provider_request_id == "req-wave-008b"
    assert usage[0].outcome == "success"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "outcome"),
    [
        (AppError("GENERATION_PROVIDER_TIMEOUT", "timeout", status_code=504), "timeout"),
        (AppError("PAYMENT_REQUIRED", "payment", status_code=402), "payment_required"),
        (AppError("GENERATION_PROVIDER_RATE_LIMITED", "rate", status_code=429), "rate_limited"),
        (AppError("GENERATION_PROVIDER_QUOTA_EXHAUSTED", "quota", status_code=429), "quota_exhausted"),
        (AppError("GENERATION_PROVIDER_INVALID_RESPONSE", "invalid", status_code=502), "invalid_response"),
    ],
)
async def test_advisor_failure_records_only_final_outcome(client, monkeypatch, error, outcome) -> None:
    provider = UsageProvider(failure=error)
    monkeypatch.setattr("app.business.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    response = await client.post(
        f"/api/v1/businesses/{business_id}/advisor", headers={"X-Workspace-Id": WORKSPACE_ID},
        json={"text": "Dame una recomendación"},
    )
    assert response.status_code == error.status_code
    assert provider.calls == 1
    usage = await _usage()
    assert len(usage) == 1 and usage[0].outcome == outcome


@pytest.mark.asyncio
async def test_advisor_failed_reservation_is_retryable_without_provider_usage(client) -> None:
    business_id = await _business(client)
    key = "advisor-balanced-not-configured"
    endpoint = f"/businesses/{business_id}/advisor"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": key}
    payload = {"text": "Dame una recomendación", "quality_level": "balanced"}

    first = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)
    replay = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)

    assert first.status_code == replay.status_code == 400
    assert await _idempotency_status(endpoint, key) == "failed"
    assert await _usage() == []


@pytest.mark.asyncio
async def test_advisor_provider_failure_marks_failed_and_replay_executes_again(client, monkeypatch) -> None:
    provider = FailOnceProvider()
    monkeypatch.setattr("app.business.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    key = "advisor-provider-retry"
    endpoint = f"/businesses/{business_id}/advisor"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": key}
    payload = {"text": "Dame una recomendación"}

    failed = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)
    assert failed.status_code == 503
    assert await _idempotency_status(endpoint, key) == "failed"
    succeeded = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)

    assert succeeded.status_code == 200
    assert provider.calls == 2
    assert await _idempotency_status(endpoint, key) == "completed"


@pytest.mark.asyncio
async def test_copywriter_unavailable_provider_does_not_leave_processing(client, monkeypatch) -> None:
    business_id = await _business(client)
    conversation = await client.post(
        "/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID},
        json={"business_id": business_id, "title": "Unavailable provider"},
    )
    conversation_id = conversation.json()["id"]
    key = "copywriter-provider-not-configured"
    endpoint = f"/conversations/{conversation_id}/messages"
    monkeypatch.setattr(
        "app.conversations.routes.get_content_provider",
        lambda **kwargs: (_ for _ in ()).throw(
            AppError("GENERATION_PROVIDER_UNAVAILABLE", "provider unavailable", status_code=503)
        ),
    )

    response = await client.post(
        f"/api/v1{endpoint}",
        headers={"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": key},
        json={"text": "Crea un caption"},
    )

    assert response.status_code == 503
    assert await _idempotency_status(endpoint, key) == "failed"
    assert await _usage() == []


@pytest.mark.asyncio
async def test_copywriter_provider_failure_retries_once_then_replays_success(client, monkeypatch) -> None:
    provider = FailOnceProvider()
    monkeypatch.setattr("app.conversations.routes.get_content_provider", lambda **kwargs: provider)
    business_id = await _business(client)
    conversation = await client.post(
        "/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID},
        json={"business_id": business_id, "title": "Provider retry"},
    )
    conversation_id = conversation.json()["id"]
    key = "copywriter-provider-retry"
    endpoint = f"/conversations/{conversation_id}/messages"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": key}
    payload = {"text": "Crea un caption"}

    failed = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)
    assert failed.status_code == 503
    assert await _idempotency_status(endpoint, key) == "failed"
    succeeded = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)
    replay = await client.post(f"/api/v1{endpoint}", headers=headers, json=payload)

    assert succeeded.status_code == replay.status_code == 200
    assert succeeded.json() == replay.json()
    assert provider.calls == 2
    assert await _idempotency_status(endpoint, key) == "completed"
    usage = await _usage()
    assert len(usage) == 2
