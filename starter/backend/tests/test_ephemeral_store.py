from __future__ import annotations

import json

import httpx
import pytest

import app.core.ephemeral_store as ephemeral_store
from app.core.config import settings
from app.core.ephemeral_store import (
    DisabledEphemeralStore,
    MemoryEphemeralStore,
    RedisEphemeralStore,
    UpstashRestEphemeralStore,
)
from app.core.errors import AppError


@pytest.mark.asyncio
async def test_disabled_ephemeral_store_is_an_explicit_noop() -> None:
    store = DisabledEphemeralStore()

    await store.set(key="cache:item", value="value")

    assert await store.get(key="cache:item") is None


@pytest.mark.asyncio
async def test_memory_ephemeral_store_applies_prefix_and_ttl() -> None:
    now = [100.0]
    store = MemoryEphemeralStore(prefix="hitrendy:test", now=lambda: now[0])

    await store.set(key="cache:item", value="value", ttl_seconds=2)
    assert await store.get(key="cache:item") == "value"
    assert "hitrendy:test:cache:item" in store._values

    now[0] = 102.1
    assert await store.get(key="cache:item") is None


@pytest.mark.asyncio
async def test_redis_ephemeral_store_uses_prefix_and_expiry() -> None:
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.expiry: dict[str, int] = {}

        async def set(self, key: str, value: str, ex: int) -> None:
            self.values[key] = value
            self.expiry[key] = ex

        async def get(self, key: str) -> str | None:
            return self.values.get(key)

        async def delete(self, key: str) -> None:
            self.values.pop(key, None)

        async def ping(self) -> bool:
            return True

    client = FakeRedis()
    store = RedisEphemeralStore(client, prefix="hitrendy:staging", default_ttl_seconds=30)

    await store.set(key="cache:item", value="value")
    assert client.values == {"hitrendy:staging:cache:item": "value"}
    assert client.expiry["hitrendy:staging:cache:item"] == 30
    assert await store.get(key="cache:item") == "value"
    await store.delete(key="cache:item")
    assert await store.get(key="cache:item") is None


@pytest.mark.asyncio
async def test_upstash_rest_store_posts_json_commands_without_values_in_urls() -> None:
    calls: list[httpx.Request] = []
    secret_value = "contenido-privado"

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        command = json.loads(request.content)
        if command[0] == "GET":
            return httpx.Response(200, json={"result": "value"})
        return httpx.Response(200, json={"result": "OK"})

    store = UpstashRestEphemeralStore(
        base_url="https://redis.upstash.io",
        token="rest-token",
        prefix="hitrendy:test",
        default_ttl_seconds=30,
        transport=httpx.MockTransport(handler),
    )

    await store.set(key="cache:item", value=secret_value, ttl_seconds=9)
    assert await store.get(key="cache:item") == "value"
    await store.delete(key="cache:item")
    await store.ensure_available()

    assert [request.method for request in calls] == ["POST", "POST", "POST", "POST"]
    assert all(request.url.path in {"", "/"} and not request.url.query for request in calls)
    assert all(secret_value not in str(request.url) for request in calls)
    assert [json.loads(request.content) for request in calls] == [
        ["SET", "hitrendy:test:cache:item", secret_value, "EX", "9"],
        ["GET", "hitrendy:test:cache:item"],
        ["DEL", "hitrendy:test:cache:item"],
        ["PING"],
    ]


@pytest.mark.asyncio
async def test_upstash_rest_store_normalizes_timeout_and_invalid_response_without_secrets() -> None:
    token = "rest-token-no-filtrar"
    value = "valor-no-filtrar"

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    unavailable = UpstashRestEphemeralStore(
        base_url="https://redis.upstash.io",
        token=token,
        prefix="hitrendy:test",
        default_ttl_seconds=30,
        transport=httpx.MockTransport(timeout_handler),
    )
    with pytest.raises(AppError) as caught:
        await unavailable.set(key="cache:item", value=value)
    assert caught.value.code == "REDIS_UNAVAILABLE"
    assert token not in caught.value.message
    assert value not in caught.value.message

    invalid_response = UpstashRestEphemeralStore(
        base_url="https://redis.upstash.io",
        token=token,
        prefix="hitrendy:test",
        default_ttl_seconds=30,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not-json")),
    )
    with pytest.raises(AppError) as caught:
        await invalid_response.ensure_available()
    assert caught.value.code == "REDIS_UNAVAILABLE"
    assert token not in caught.value.message


def test_upstash_token_rotation_rebuilds_the_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "redis_provider", "redis")
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(settings, "upstash_redis_rest_url", "https://redis.upstash.io")
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "token-anterior")
    monkeypatch.setattr(settings, "redis_prefix", "hitrendy:test")
    monkeypatch.setattr(settings, "redis_default_ttl_seconds", 30)
    monkeypatch.setattr(ephemeral_store, "_store", None)
    monkeypatch.setattr(ephemeral_store, "_store_configuration", None)

    first = ephemeral_store.get_ephemeral_store()
    monkeypatch.setattr(settings, "upstash_redis_rest_token", "token-rotado")
    second = ephemeral_store.get_ephemeral_store()

    assert isinstance(first, UpstashRestEphemeralStore)
    assert isinstance(second, UpstashRestEphemeralStore)
    assert second is not first
