from __future__ import annotations

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from hashlib import sha256
from time import monotonic
from uuid import uuid4

from app.core.ephemeral_store import EphemeralStore
from app.trends.contracts import SourceCandidate, SourceEvidence, SourceFetchResult, valid_result

CACHE_FORMAT = "trend-source-v1"
MAX_CACHE_VALUE_BYTES = 64_000
DEFAULT_OPERATION_DEADLINE_SECONDS = 30.0
LEASE_DEADLINE_MARGIN_SECONDS = 5.0
LEASE_POLL_SECONDS = 0.05


class CacheLeaseBusy(Exception):
    """Another worker is populating this key; retry after its bounded lease."""


def cache_key(
    *,
    source: str,
    adapter_version: str,
    region: str,
    category: str | None,
    query: str,
    public_parameters: tuple[str, ...] = (),
) -> str:
    material = "\x1f".join(
        (
            CACHE_FORMAT,
            source,
            adapter_version,
            region.strip().upper(),
            category.strip().casefold() if category else "",
            " ".join(query.split()).casefold(),
            *(" ".join(parameter.split()).casefold() for parameter in sorted(public_parameters)),
        )
    )
    return f"trends:source:{sha256(material.encode()).hexdigest()}"


def _encode(result: SourceFetchResult) -> str | None:
    payload = {
        "format": CACHE_FORMAT,
        "status": str(result.status),
        "candidates": [
            {
                "title": candidate.title,
                "summary": candidate.summary,
                "region": candidate.region,
                "category": candidate.category,
                "observed_at": candidate.observed_at.astimezone(UTC).isoformat(),
                "evidence": [
                    {
                        "source_url": evidence.source_url,
                        "observed_at": evidence.observed_at.astimezone(UTC).isoformat(),
                        "region": evidence.region,
                        "confidence": evidence.confidence,
                    }
                    for evidence in candidate.evidence
                ],
            }
            for candidate in result.candidates
        ],
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return encoded if len(encoded.encode()) <= MAX_CACHE_VALUE_BYTES else None


def _decode(value: str) -> SourceFetchResult | None:
    try:
        payload = json.loads(value)
        if not isinstance(payload, dict) or payload.get("format") != CACHE_FORMAT:
            return None
        raw_candidates = payload.get("candidates")
        if not isinstance(raw_candidates, list):
            return None
        candidates = tuple(
            SourceCandidate(
                title=item["title"],
                summary=item["summary"],
                region=item["region"],
                category=item["category"],
                observed_at=datetime.fromisoformat(item["observed_at"]),
                evidence=tuple(
                    SourceEvidence(
                        source_url=evidence["source_url"],
                        observed_at=datetime.fromisoformat(evidence["observed_at"]),
                        region=evidence["region"],
                        confidence=evidence["confidence"],
                    )
                    for evidence in item["evidence"]
                ),
            )
            for item in raw_candidates
        )
        validated = valid_result(SourceFetchResult(payload["status"], candidates))
        return validated.result if validated and not validated.invalid_candidates else None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class TrendSourceCache:
    """Best-effort sanitized cache; Redis failure never prevents a source call."""

    def __init__(self, store: EphemeralStore) -> None:
        self.store = store
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_users: dict[str, int] = {}

    async def get(self, key: str) -> SourceFetchResult | None:
        try:
            value = await self.store.get(key=key)
        except Exception:
            return None
        return _decode(value) if value else None

    async def set(self, key: str, result: SourceFetchResult, *, ttl_seconds: int) -> None:
        encoded = _encode(result)
        if encoded is None:
            return
        try:
            await self.store.set(key=key, value=encoded, ttl_seconds=ttl_seconds)
        except Exception:
            return

    async def coalesce(
        self,
        key: str,
        fetch: Callable[[], Awaitable[SourceFetchResult]],
        *,
        operation_deadline_seconds: float = DEFAULT_OPERATION_DEADLINE_SECONDS,
    ) -> SourceFetchResult:
        if operation_deadline_seconds <= 0:
            raise ValueError("El deadline de la fuente debe ser positivo.")
        lock = self._locks.setdefault(key, asyncio.Lock())
        self._lock_users[key] = self._lock_users.get(key, 0) + 1
        try:
            async with lock:
                cached = await self.get(key)
                if cached is not None:
                    return cached
                return await self._with_lease(
                    key,
                    fetch,
                    operation_deadline_seconds=operation_deadline_seconds,
                )
        finally:
            # Do not retain one local lock per historical cache key forever.
            self._lock_users[key] -= 1
            if self._lock_users[key] == 0 and self._locks.get(key) is lock:
                self._locks.pop(key, None)
                self._lock_users.pop(key, None)

    async def _with_lease(
        self,
        key: str,
        fetch: Callable[[], Awaitable[SourceFetchResult]],
        *,
        operation_deadline_seconds: float,
    ) -> SourceFetchResult:
        token = uuid4().hex
        lease_key = f"{key}:lease"
        lease_ttl_seconds = math.ceil(
            operation_deadline_seconds + LEASE_DEADLINE_MARGIN_SECONDS
        )

        async def bounded_fetch() -> SourceFetchResult:
            async with asyncio.timeout(operation_deadline_seconds):
                return await fetch()

        try:
            acquired = await self.store.acquire_lease(
                key=lease_key,
                token=token,
                ttl_seconds=lease_ttl_seconds,
            )
        except Exception:
            # Redis is optional: local coalescing remains useful when it is down.
            return await bounded_fetch()
        if acquired is None:
            return await bounded_fetch()
        if acquired:
            try:
                return await bounded_fetch()
            finally:
                await self._release(lease_key, token)

        # The owner cannot legitimately outlive its operation deadline. The
        # lease includes a safety margin, and waiters poll for the cached
        # result for that complete bounded lifetime instead of failing after
        # an unrelated fixed delay.
        deadline = monotonic() + lease_ttl_seconds + LEASE_POLL_SECONDS
        while monotonic() < deadline:
            await asyncio.sleep(LEASE_POLL_SECONDS)
            cached = await self.get(key)
            if cached is not None:
                return cached
            try:
                acquired = await self.store.acquire_lease(
                    key=lease_key,
                    token=token,
                    ttl_seconds=lease_ttl_seconds,
                )
            except Exception:
                return await bounded_fetch()
            if acquired is None:
                return await bounded_fetch()
            if acquired:
                try:
                    return await bounded_fetch()
                finally:
                    await self._release(lease_key, token)
        raise CacheLeaseBusy()

    async def _release(self, key: str, token: str) -> None:
        try:
            await self.store.release_lease(key=key, token=token)
        except Exception:
            return None
