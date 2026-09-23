from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.infrastructure import get_infrastructure_capabilities


@pytest.mark.asyncio
async def test_capabilities_report_disabled_storage_and_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "object_storage_provider", "disabled")
    monkeypatch.setattr(settings, "redis_provider", "disabled")

    assert await get_infrastructure_capabilities() == {
        "storage": "disabled",
        "redis": "disabled",
    }


@pytest.mark.asyncio
async def test_capabilities_can_distinguish_unconfigured_remote_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "object_storage_provider", "supabase")
    monkeypatch.setattr(settings, "supabase_url", "")
    monkeypatch.setattr(settings, "supabase_service_role_key", "")
    monkeypatch.setattr(settings, "redis_provider", "redis")
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "upstash_redis_rest_url", "")
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "")

    assert await get_infrastructure_capabilities() == {
        "storage": "unconfigured",
        "redis": "unconfigured",
    }


@pytest.mark.asyncio
async def test_capabilities_report_optional_redis_degradation_without_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenStore:
        async def ensure_available(self) -> None:
            raise RuntimeError("redis://secret@private-host")

    monkeypatch.setattr(settings, "object_storage_provider", "disabled")
    monkeypatch.setattr(settings, "redis_provider", "redis")
    monkeypatch.setattr(settings, "redis_url", "rediss://redis.example.com:6379/0")
    monkeypatch.setattr(settings, "redis_required", False)
    monkeypatch.setattr("app.core.infrastructure.get_ephemeral_store", lambda: BrokenStore())

    assert await get_infrastructure_capabilities() == {
        "storage": "disabled",
        "redis": "degraded",
    }


@pytest.mark.asyncio
async def test_readiness_fails_when_required_redis_is_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "redis_required", True)
    monkeypatch.setattr(
        "app.main.get_infrastructure_capabilities",
        lambda: _capabilities_with_required_redis_error(),
    )

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "ok", "storage": "available", "redis": "error"},
    }


async def _capabilities_with_required_redis_error() -> dict[str, str]:
    return {"storage": "available", "redis": "error"}
