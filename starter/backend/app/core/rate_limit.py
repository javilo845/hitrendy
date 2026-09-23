from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Protocol

from app.core.errors import AppError


class RateLimiter(Protocol):
    async def allow(self, *, key: str, limit: int, window_seconds: int) -> bool: ...

    async def ensure_available(self) -> None: ...


class LocalRateLimiter:
    """Process-local limiter used only by development and deterministic tests."""

    def __init__(self) -> None:
        self.windows: dict[str, list[float]] = defaultdict(list)

    async def allow(self, *, key: str, limit: int, window_seconds: int) -> bool:
        now = monotonic()
        window = [item for item in self.windows[key] if now - item < window_seconds]
        if len(window) >= limit:
            self.windows[key] = window
            return False
        window.append(now)
        self.windows[key] = window
        return True

    async def ensure_available(self) -> None:
        return None


class RedisRateLimiter:
    """Fixed-window Redis limiter shared by every API instance."""

    _INCREMENT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

    def __init__(
        self,
        execute: Callable[[str, int, str, int], Awaitable[int]],
        ping: Callable[[], Awaitable[bool]],
    ) -> None:
        self._execute = execute
        self._ping = ping

    @classmethod
    def from_url(cls, url: str) -> RedisRateLimiter:
        import redis.asyncio as redis

        client = redis.from_url(url, decode_responses=True)

        async def execute(script: str, key_count: int, key: str, window_seconds: int) -> int:
            return int(await client.eval(script, key_count, key, window_seconds))

        return cls(execute, client.ping)

    async def allow(self, *, key: str, limit: int, window_seconds: int) -> bool:
        try:
            count = await self._execute(self._INCREMENT_SCRIPT, 1, key, window_seconds)
        except Exception as exc:
            raise AppError(
                "RATE_LIMIT_UNAVAILABLE",
                "No pudimos verificar el límite de solicitudes. Inténtalo nuevamente.",
                status_code=503,
                retryable=True,
            ) from exc
        return count <= limit

    async def ensure_available(self) -> None:
        try:
            await self._ping()
        except Exception as exc:
            raise RuntimeError("El limitador compartido no está disponible.") from exc
