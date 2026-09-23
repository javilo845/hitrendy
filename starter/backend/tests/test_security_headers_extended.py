from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_security_headers_on_public_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert "permissions-policy" in response.headers
    assert "camera" in response.headers.get("permissions-policy", "")
    assert response.headers.get("x-request-id") is not None


@pytest.mark.asyncio
async def test_security_headers_on_error() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"


@pytest.mark.asyncio
@pytest.mark.parametrize("app_env", ["development", "test"])
async def test_no_hsts_outside_production_like(monkeypatch, app_env: str) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", app_env)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.get("/health/live")
    assert "strict-transport-security" not in response.headers


@pytest.mark.asyncio
async def test_hsts_requires_production_like_https(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.get("/health/live")
    assert "strict-transport-security" in response.headers


@pytest.mark.asyncio
async def test_hsts_is_absent_for_production_like_http(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "staging")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
    assert "strict-transport-security" not in response.headers


@pytest.mark.asyncio
async def test_internal_error_has_stable_cors_and_security_headers(caplog) -> None:
    caplog.set_level(logging.INFO, logger="hitrendy.http")
    async def failing_endpoint() -> None:
        raise RuntimeError("test failure")

    app.add_api_route("/__test_internal_failure", failing_endpoint, methods=["GET"])
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/__test_internal_failure",
                headers={"Origin": "http://localhost:3000"},
            )
        assert response.status_code == 500
        assert response.json() == {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Ocurrió un error interno.",
                "retryable": True,
            }
        }
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
        assert response.headers.get("access-control-allow-credentials") == "true"
        assert response.headers.get("x-content-type-options") == "nosniff"
        assert response.headers.get("x-frame-options") == "DENY"
        assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
        assert response.headers.get("x-request-id")
        assert sum(record.message == "http_request_failed" for record in caplog.records) == 1
        assert sum(record.message == "http_request" for record in caplog.records) == 1
    finally:
        app.router.routes.pop()


@pytest.mark.asyncio
async def test_internal_error_does_not_reflect_disallowed_origin() -> None:
    async def failing_endpoint() -> None:
        raise RuntimeError("test failure")

    app.add_api_route("/__test_internal_failure_origin", failing_endpoint, methods=["GET"])
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/__test_internal_failure_origin",
                headers={"Origin": "https://evil.example.com"},
            )
        assert response.status_code == 500
        assert response.headers.get("access-control-allow-origin") is None
    finally:
        app.router.routes.pop()


@pytest.mark.asyncio
async def test_health_does_not_leak_secrets(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    body = response.text.lower()
    assert "password" not in body
    assert "secret" not in body
    assert "token" not in body
    assert "key" not in body


@pytest.mark.asyncio
async def test_ready_does_not_leak_internal_details(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    body = response.text.lower()
    assert "url" not in body
    assert "host" not in body or "host" in ["localhost"] and "host" in body
    assert "bucket" not in body
    assert "secret" not in body
    assert "token" not in body
