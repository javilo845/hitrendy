from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.main import _rate_windows


@pytest.mark.asyncio
async def test_security_headers_and_request_id(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


@pytest.mark.asyncio
async def test_request_log_contains_safe_correlation_fields(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="hitrendy.http")
    response = await client.get("/health/live")

    record = next(item for item in caplog.records if item.name == "hitrendy.http")
    assert response.headers["x-request-id"] == record.request_id
    assert record.method == "GET"
    assert record.path == "/health/live"
    assert record.status_code == 200
    assert record.duration_ms >= 0


@pytest.mark.asyncio
async def test_readiness_checks_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "storage": "available", "redis": "available"},
    }


@pytest.mark.asyncio
async def test_readiness_fails_closed_when_database_is_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("database unavailable")

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("app.main.get_session_factory", lambda: lambda: BrokenSession())
    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "unavailable"},
    }


@pytest.mark.asyncio
async def test_malformed_content_length_returns_safe_error(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"Content-Length": "not-a-number"})

    assert response.status_code == 400
    assert response.headers["x-request-id"]
    assert response.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"


@pytest.mark.asyncio
async def test_login_rate_limit_returns_retryable_error(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _rate_windows.clear()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    try:
        first = await client.post(
            "/api/v1/auth/login",
            json={"email": "nadie@example.com", "password": "incorrecta"},
        )
        second = await client.post(
            "/api/v1/auth/login",
            json={"email": "nadie@example.com", "password": "incorrecta"},
        )
    finally:
        _rate_windows.clear()

    assert first.status_code in {401, 403}
    assert second.status_code == 429
    assert second.headers["retry-after"]
    assert second.json()["error"]["code"] == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_visual_analysis_is_rate_limited_before_processing(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _rate_windows.clear()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    try:
        first = await client.post("/api/v1/assets/not-an-asset/analyses")
        second = await client.post("/api/v1/assets/not-an-asset/analyses")
    finally:
        _rate_windows.clear()

    assert first.status_code == 404
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"


def test_production_configuration_fails_closed_for_insecure_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jwt_secret", "replace-in-local-env")

    with pytest.raises(RuntimeError, match="configuración de producción"):
        settings.validate_runtime_configuration()
