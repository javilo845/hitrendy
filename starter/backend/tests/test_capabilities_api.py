from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_get_capabilities_returns_snapshot() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    for cap in ("advisor", "copywriter", "vision_review", "image_generation", "video_generation", "trend_analysis"):
        assert cap in data, f"Falta {cap} en snapshot"


@pytest.mark.asyncio
async def test_capabilities_no_secrets() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    body = response.text.lower()
    for secret_word in ("api_key", "secret", "token", "password", "database_url", "redis_url"):
        assert secret_word not in body, f"Respuesta contiene '{secret_word}'"


@pytest.mark.asyncio
async def test_capabilities_cache_control() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    cc = response.headers.get("cache-control", "")
    assert "private" in cc
    assert "no-store" in cc


@pytest.mark.asyncio
async def test_capabilities_is_get_only() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = await client.request(method, "/api/v1/capabilities")
            assert response.status_code in {405, 400}, f"{method} debería fallar"


@pytest.mark.asyncio
async def test_capabilities_structure() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    data = response.json()
    advisor = data["advisor"]
    expected_fields = {"status", "tier", "quality_levels"}
    assert expected_fields.issubset(advisor.keys()), f"Faltan campos en advisor: {advisor.keys()}"


@pytest.mark.asyncio
async def test_capabilities_no_external_call() -> None:
    """Verify the snapshot is derived solely from config and outcome store.

    Block the real provider and generation entrypoints while leaving the
    imported ASGI client available for the test request itself.
    """
    async def forbid_external_execution(*args: object, **kwargs: object) -> None:
        raise AssertionError("External provider execution is forbidden")

    with (
        patch("app.providers.content.OpenAICompatibleContentModelProvider.generate_social_post", forbid_external_execution),
        patch("app.providers.content.OpenAICompatibleContentModelProvider.repair_social_post", forbid_external_execution),
        patch(
            "app.providers.content.OpenAICompatibleContentModelProvider.generate_short_video_script",
            forbid_external_execution,
        ),
        patch(
            "app.providers.content.OpenAICompatibleContentModelProvider.repair_short_video_script",
            forbid_external_execution,
        ),
        patch("app.providers.content.OpenAICompatibleContentModelProvider._complete", forbid_external_execution),
        patch("app.providers.vision.OpenAICompatibleVisionReviewProvider.analyze", forbid_external_execution),
        patch("app.services.generate_social_post.GenerateSocialPostService.execute", forbid_external_execution),
        patch("app.services.generate_social_post.GenerateSocialPostService.execute_variation", forbid_external_execution),
        patch("app.services.generate_short_video_script.GenerateShortVideoScriptService.execute", forbid_external_execution),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_capabilities_security_headers_present() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert "x-content-type-options" in response.headers
    assert "x-frame-options" in response.headers
    assert "referrer-policy" in response.headers


@pytest.mark.asyncio
async def test_capabilities_response_model_no_provider_key() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/capabilities")
    assert response.status_code == 200
    body = response.text
    assert "provider_key" not in body
    assert "provider" not in body


@pytest.mark.asyncio
async def test_capabilities_not_contaminated_by_previous_outcomes() -> None:
    """The endpoint uses NullCapabilityOutcomeStore, so it's never contaminated."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response1 = await client.get("/api/v1/capabilities")
        response2 = await client.get("/api/v1/capabilities")
    assert response1.json() == response2.json()
