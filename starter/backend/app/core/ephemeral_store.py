from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.errors import AppError


class EphemeralStore(Protocol):
    async def get(self, *, key: str) -> str | None: ...

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, *, key: str) -> None: ...

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None: ...

    async def release_lease(self, *, key: str, token: str) -> None: ...

    async def ensure_available(self) -> None: ...


class DisabledEphemeralStore:
    """Explicit no-op adapter for optional cache and coordination features."""

    async def get(self, *, key: str) -> str | None:
        del key
        return None

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        del key, value, ttl_seconds

    async def delete(self, *, key: str) -> None:
        del key

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        del key, token, ttl_seconds
        return None

    async def release_lease(self, *, key: str, token: str) -> None:
        del key, token

    async def ensure_available(self) -> None:
        return None


class MemoryEphemeralStore:
    """Process-local TTL store for development and tests; never distributed."""

    def __init__(self, *, prefix: str, now: Callable[[], float] = monotonic) -> None:
        self._prefix = _normalize_prefix(prefix)
        self._now = now
        self._values: dict[str, tuple[str, float]] = {}

    def _key(self, key: str) -> str:
        return f"{self._prefix}{_validate_key(key)}"

    async def get(self, *, key: str) -> str | None:
        entry = self._values.get(self._key(key))
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at <= self._now():
            await self.delete(key=key)
            return None
        return value

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else settings.redis_default_ttl_seconds
        if ttl <= 0:
            raise ValueError("El TTL debe ser positivo.")
        self._values[self._key(key)] = (value, self._now() + ttl)

    async def delete(self, *, key: str) -> None:
        self._values.pop(self._key(key), None)

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        if ttl_seconds <= 0:
            raise ValueError("El TTL debe ser positivo.")
        lease_key = self._key(key)
        current = self._values.get(lease_key)
        if current is not None and current[1] > self._now():
            return False
        self._values[lease_key] = (token, self._now() + ttl_seconds)
        return True

    async def release_lease(self, *, key: str, token: str) -> None:
        lease_key = self._key(key)
        current = self._values.get(lease_key)
        if current is not None and current[0] == token:
            self._values.pop(lease_key, None)

    async def ensure_available(self) -> None:
        return None


class RedisEphemeralStore:
    def __init__(self, client, *, prefix: str, default_ttl_seconds: int) -> None:
        self._client = client
        self._prefix = _normalize_prefix(prefix)
        self._default_ttl_seconds = default_ttl_seconds

    @classmethod
    def from_url(cls, *, url: str, prefix: str, default_ttl_seconds: int) -> RedisEphemeralStore:
        import redis.asyncio as redis

        return cls(
            redis.from_url(url, decode_responses=True),
            prefix=prefix,
            default_ttl_seconds=default_ttl_seconds,
        )

    def _key(self, key: str) -> str:
        return f"{self._prefix}{_validate_key(key)}"

    async def get(self, *, key: str) -> str | None:
        try:
            value = await self._client.get(self._key(key))
            return str(value) if value is not None else None
        except Exception as exc:
            raise _redis_error(exc) from exc

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        if ttl <= 0:
            raise ValueError("El TTL debe ser positivo.")
        try:
            await self._client.set(self._key(key), value, ex=ttl)
        except Exception as exc:
            raise _redis_error(exc) from exc

    async def delete(self, *, key: str) -> None:
        try:
            await self._client.delete(self._key(key))
        except Exception as exc:
            raise _redis_error(exc) from exc

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        if ttl_seconds <= 0:
            raise ValueError("El TTL debe ser positivo.")
        try:
            return bool(await self._client.set(self._key(key), token, nx=True, ex=ttl_seconds))
        except Exception as exc:
            raise _redis_error(exc) from exc

    async def release_lease(self, *, key: str, token: str) -> None:
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        try:
            await self._client.eval(script, 1, self._key(key), token)
        except Exception as exc:
            raise _redis_error(exc) from exc

    async def ensure_available(self) -> None:
        try:
            await self._client.ping()
        except Exception as exc:
            raise _redis_error(exc) from exc


class UpstashRestEphemeralStore:
    """Small REST adapter for Upstash when a TCP Redis URL is unavailable."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        prefix: str,
        default_ttl_seconds: int,
        timeout_seconds: float = 5,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._prefix = _normalize_prefix(prefix)
        self._default_ttl_seconds = default_ttl_seconds
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _key(self, key: str) -> str:
        return f"{self._prefix}{_validate_key(key)}"

    async def _command(self, *parts: str) -> object:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._base_url,
                    headers={"Authorization": f"Bearer {self._token}"},
                    json=list(parts),
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or "result" not in payload:
                raise ValueError("Respuesta Redis inválida.")
            return payload["result"]
        except (httpx.HTTPError, ValueError) as exc:
            raise _redis_error(exc) from exc

    async def get(self, *, key: str) -> str | None:
        value = await self._command("GET", self._key(key))
        return str(value) if value is not None else None

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        if ttl <= 0:
            raise ValueError("El TTL debe ser positivo.")
        await self._command("SET", self._key(key), value, "EX", str(ttl))

    async def delete(self, *, key: str) -> None:
        await self._command("DEL", self._key(key))

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        if ttl_seconds <= 0:
            raise ValueError("El TTL debe ser positivo.")
        result = await self._command("SET", self._key(key), token, "NX", "EX", str(ttl_seconds))
        return result == "OK"

    async def release_lease(self, *, key: str, token: str) -> None:
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end"
        )
        await self._command("EVAL", script, "1", self._key(key), token)

    async def ensure_available(self) -> None:
        await self._command("PING")


def _normalize_prefix(prefix: str) -> str:
    return f"{prefix.rstrip(':')}:"


def _validate_key(key: str) -> str:
    if not key or key.startswith(":") or any(character.isspace() for character in key):
        raise ValueError("La clave efímera no es válida.")
    return key


def _redis_error(exc: Exception) -> AppError:
    return AppError(
        "REDIS_UNAVAILABLE",
        "El almacenamiento temporal no está disponible. Inténtalo nuevamente.",
        status_code=503,
        retryable=True,
    )


_store: EphemeralStore | None = None
_store_configuration: tuple[str, str, str, str, str, str] | None = None


def get_ephemeral_store() -> EphemeralStore:
    global _store, _store_configuration
    configuration = (
        settings.redis_provider,
        settings.redis_url,
        settings.upstash_redis_rest_url,
        settings.upstash_redis_rest_token,
        settings.redis_prefix,
        str(settings.redis_default_ttl_seconds),
    )
    if _store is not None and _store_configuration == configuration:
        return _store

    if settings.redis_provider == "disabled":
        store: EphemeralStore = DisabledEphemeralStore()
    elif settings.redis_provider == "memory":
        store = MemoryEphemeralStore(prefix=settings.redis_prefix)
    elif settings.redis_url:
        store = RedisEphemeralStore.from_url(
            url=settings.redis_url,
            prefix=settings.redis_prefix,
            default_ttl_seconds=settings.redis_default_ttl_seconds,
        )
    else:
        store = UpstashRestEphemeralStore(
            base_url=settings.upstash_redis_rest_url,
            token=settings.upstash_redis_rest_token,
            prefix=settings.redis_prefix,
            default_ttl_seconds=settings.redis_default_ttl_seconds,
        )
    _store = store
    _store_configuration = configuration
    return store
