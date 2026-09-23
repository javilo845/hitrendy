from __future__ import annotations

import httpx
import pytest

from app.core.ephemeral_store import MemoryEphemeralStore
from app.providers.content import OpenAICompatibleContentModelProvider
from app.providers.openrouter_catalog import OpenRouterModelCatalog


def _remote_payload() -> dict[str, object]:
    return {
        "data": [
            {
                "id": "provider/model-a",
                "name": "Model A",
                "context_length": 8192,
                "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                "supported_parameters": ["response_format", "temperature"],
            }
        ]
    }


@pytest.mark.asyncio
async def test_catalog_caches_remote_result_and_returns_typed_prices() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/api/v1/models"
        return httpx.Response(200, json=_remote_payload())

    provider = OpenAICompatibleContentModelProvider(
        base_url="https://openrouter.example/api/v1", api_key="catalog-secret", model_name="openrouter/free",
        provider_name="openrouter", transport=httpx.MockTransport(handler),
    )
    catalog = OpenRouterModelCatalog(ttl_seconds=30, store=MemoryEphemeralStore(prefix="catalog-cache"), fetcher=provider.fetch_model_catalog)
    first = await catalog.list_models()
    second = await catalog.list_models()

    assert calls == 1
    assert first == second
    assert first[0].prompt_price is not None
    assert first[0].structured_output_support is True


@pytest.mark.asyncio
async def test_catalog_expires_and_refetches() -> None:
    now = [0.0]
    calls = 0

    async def fetcher() -> list[object]:
        nonlocal calls
        calls += 1
        return [{"id": "a/model", "name": "A"}]

    catalog = OpenRouterModelCatalog(
        ttl_seconds=10,
        store=MemoryEphemeralStore(prefix="catalog-expiry", now=lambda: now[0]),
        fetcher=fetcher,
    )
    await catalog.list_models()
    now[0] = 11.0
    await catalog.list_models()

    assert calls == 2


@pytest.mark.asyncio
async def test_catalog_tolerates_remote_failure_and_invalid_payload() -> None:
    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="internal provider detail")

    unavailable_provider = OpenAICompatibleContentModelProvider(
        base_url="https://openrouter.example/api/v1", api_key="catalog-secret", model_name="openrouter/free",
        provider_name="openrouter", transport=httpx.MockTransport(unavailable),
    )
    unavailable_catalog = OpenRouterModelCatalog(
        ttl_seconds=10,
        store=MemoryEphemeralStore(prefix="catalog-unavailable"),
        fetcher=unavailable_provider.fetch_model_catalog,
    )
    assert await unavailable_catalog.list_models() == []

    async def invalid_fetcher() -> list[object]:
        return [{"id": 1}]

    invalid_catalog = OpenRouterModelCatalog(
        ttl_seconds=10,
        store=MemoryEphemeralStore(prefix="catalog-invalid"),
        fetcher=invalid_fetcher,
    )
    assert await invalid_catalog.list_models() == []
