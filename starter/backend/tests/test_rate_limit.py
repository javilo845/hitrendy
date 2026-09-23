from __future__ import annotations

import pytest

from app.core.rate_limit import LocalRateLimiter, RedisRateLimiter


@pytest.mark.asyncio
async def test_local_rate_limiter_rejects_after_the_configured_window_capacity() -> None:
    limiter = LocalRateLimiter()

    assert await limiter.allow(key="login", limit=1, window_seconds=60)
    assert not await limiter.allow(key="login", limit=1, window_seconds=60)


@pytest.mark.asyncio
async def test_redis_rate_limiter_uses_an_atomic_increment_with_expiry() -> None:
    calls: list[tuple[str, int, str, int]] = []

    async def execute(script: str, key_count: int, key: str, window_seconds: int) -> int:
        calls.append((script, key_count, key, window_seconds))
        return 2

    async def ping() -> bool:
        return True

    limiter = RedisRateLimiter(execute, ping)

    assert await limiter.allow(key="hitrendy:rate-limit:login", limit=2, window_seconds=60)
    assert calls[0][1:] == (1, "hitrendy:rate-limit:login", 60)
    assert "EXPIRE" in calls[0][0]
