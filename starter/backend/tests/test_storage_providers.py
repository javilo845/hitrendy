from __future__ import annotations

import httpx
import pytest

from app.core.errors import AppError
from app.providers.storage import LocalObjectStorageProvider, SupabaseStorageProvider


@pytest.mark.asyncio
async def test_local_storage_put_read_exists_and_delete(tmp_path) -> None:
    provider = LocalObjectStorageProvider(str(tmp_path))
    key = "workspaces/ws_1/assets/asset.png"

    await provider.put(key=key, content=b"image", content_type="image/png")

    assert await provider.exists(key=key)
    assert await provider.read(key=key) == b"image"
    await provider.delete(key=key)
    assert not await provider.exists(key=key)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["../secret", "/etc/passwd", "workspaces/../secret", ""])
async def test_local_storage_rejects_unsafe_keys(tmp_path, key: str) -> None:
    provider = LocalObjectStorageProvider(str(tmp_path))

    with pytest.raises(ValueError, match="Invalid object storage key"):
        await provider.put(key=key, content=b"x", content_type="image/png")


@pytest.mark.asyncio
async def test_local_storage_reports_missing_file_without_exposing_path(tmp_path) -> None:
    provider = LocalObjectStorageProvider(str(tmp_path))

    with pytest.raises(AppError) as caught:
        await provider.read(key="workspaces/ws_1/assets/missing.png")

    assert caught.value.code == "ASSET_UNAVAILABLE"
    assert str(tmp_path) not in caught.value.message


@pytest.mark.asyncio
async def test_supabase_storage_uses_private_server_side_requests() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"Key": "object"})
        if request.method == "GET":
            return httpx.Response(200, content=b"stored")
        if request.method == "HEAD":
            return httpx.Response(200)
        if request.method == "DELETE":
            return httpx.Response(200, json=[])
        return httpx.Response(405)

    provider = SupabaseStorageProvider(
        base_url="https://project.supabase.co",
        service_role_key="test-service-role",
        bucket="private-assets",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )
    key = "workspaces/ws_1/assets/asset.png"

    await provider.put(key=key, content=b"stored", content_type="image/png")
    assert await provider.read(key=key) == b"stored"
    assert await provider.exists(key=key)
    await provider.delete(key=key)

    assert all("/storage/v1/object/private-assets/" in str(call.url) for call in calls[:3])
    assert calls[0].headers["authorization"] == "Bearer test-service-role"
    assert calls[0].headers["apikey"] == "test-service-role"
    assert calls[0].headers["x-upsert"] == "false"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response, expected_retryable",
    [
        (httpx.Response(401), False),
        (httpx.Response(404), False),
        (httpx.Response(503), True),
    ],
)
async def test_supabase_storage_normalizes_provider_errors(
    response: httpx.Response, expected_retryable: bool
) -> None:
    provider = SupabaseStorageProvider(
        base_url="https://project.supabase.co",
        service_role_key="secret-value",
        bucket="private-assets",
        timeout_seconds=2,
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(AppError) as caught:
        await provider.put(
            key="workspaces/ws_1/assets/asset.png",
            content=b"stored",
            content_type="image/png",
        )

    assert caught.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert caught.value.retryable is expected_retryable
    assert "secret-value" not in caught.value.message


@pytest.mark.asyncio
async def test_supabase_storage_normalizes_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    provider = SupabaseStorageProvider(
        base_url="https://project.supabase.co",
        service_role_key="secret-value",
        bucket="private-assets",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(AppError) as caught:
        await provider.read(key="workspaces/ws_1/assets/asset.png")

    assert caught.value.code == "OBJECT_STORAGE_UNAVAILABLE"
    assert caught.value.retryable is True
