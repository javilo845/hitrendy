from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.ephemeral_store import EphemeralStore, get_ephemeral_store
from app.trends.cache import TrendSourceCache
from app.trends.contracts import SourceResultStatus, TrendSource
from app.trends.quota import TrendQuotaBudget
from app.trends.real_sources import RssFeed, RssTrendSource, SerpApiTrendSource, YouTubeTrendSource

_source_caches: dict[int, TrendSourceCache] = {}
SOURCE_RUNTIME_TTL_SECONDS = 300
_PUBLIC_RUNTIME_STATUSES = {
    "available",
    "degraded",
    "quota_exhausted",
    "unavailable",
}


@dataclass(frozen=True)
class TrendSourceAvailability:
    identifier: str
    public_name: str
    source_type: str
    configured: bool
    status: str
    next_reset_at: datetime | None = None


@dataclass(frozen=True)
class SourceRuntimeState:
    status: str
    next_reset_at: datetime | None
    observed_at: datetime


class SourceRuntimeRegistry:
    """Share only sanitized, expiring source health through the ephemeral store."""

    def __init__(
        self,
        store: EphemeralStore,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.store = store
        self.now = now
        self._local: dict[str, SourceRuntimeState] = {}

    @staticmethod
    def _key(identifier: str) -> str:
        return f"trends:source-runtime:{identifier}"

    async def record(
        self,
        identifier: str,
        status: SourceResultStatus,
        next_reset_at: datetime | None = None,
    ) -> None:
        if status in {SourceResultStatus.SUCCESS, SourceResultStatus.EMPTY}:
            public_status, reset = "available", None
        elif status == SourceResultStatus.QUOTA_EXHAUSTED:
            public_status, reset = "quota_exhausted", next_reset_at
        elif status in {
            SourceResultStatus.TIMEOUT,
            SourceResultStatus.INVALID,
            SourceResultStatus.RATE_LIMITED,
        }:
            public_status, reset = "degraded", None
        else:
            public_status, reset = "unavailable", None
        observed = self.now().astimezone(UTC)
        state = SourceRuntimeState(public_status, reset, observed)
        self._local[identifier] = state
        payload = json.dumps(
            {
                "status": public_status,
                "next_reset_at": reset.astimezone(UTC).isoformat() if reset else None,
                "observed_at": observed.isoformat(),
            },
            separators=(",", ":"),
        )
        try:
            await self.store.set(
                key=self._key(identifier),
                value=payload,
                ttl_seconds=SOURCE_RUNTIME_TTL_SECONDS,
            )
        except Exception:
            return

    async def get(self, identifier: str) -> SourceRuntimeState | None:
        now = self.now().astimezone(UTC)
        shared: SourceRuntimeState | None = None
        try:
            value = await self.store.get(key=self._key(identifier))
            shared = self._decode(value) if value else None
        except Exception:
            # A shared-store incident degrades sharing, never the application.
            shared = None
        # Both views are validated observations of the same source.  The most
        # recent one wins, so a failed shared write cannot resurrect old health.
        known = [state for state in (shared, self._local.get(identifier)) if state is not None]
        state = max(known, key=lambda item: item.observed_at) if known else None
        if state is None or state.observed_at + timedelta(seconds=SOURCE_RUNTIME_TTL_SECONDS) <= now:
            self._local.pop(identifier, None)
            return None
        if (
            state.status == "quota_exhausted"
            and state.next_reset_at is not None
            and state.next_reset_at <= now
        ):
            return SourceRuntimeState("available", None, state.observed_at)
        return state

    @staticmethod
    def _decode(value: str) -> SourceRuntimeState | None:
        try:
            payload = json.loads(value)
            status = payload["status"]
            observed = datetime.fromisoformat(payload["observed_at"])
            raw_reset = payload.get("next_reset_at")
            reset = datetime.fromisoformat(raw_reset) if raw_reset else None
            if (
                status not in _PUBLIC_RUNTIME_STATUSES
                or observed.tzinfo is None
                or (reset is not None and reset.tzinfo is None)
            ):
                return None
            return SourceRuntimeState(
                status,
                reset.astimezone(UTC) if reset else None,
                observed.astimezone(UTC),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def clear(self) -> None:
        identifiers = tuple(self._local)
        self._local.clear()
        for identifier in identifiers:
            try:
                await self.store.delete(key=self._key(identifier))
            except Exception:
                continue


_source_runtime_registries: dict[int, SourceRuntimeRegistry] = {}


def _runtime_registry(store: EphemeralStore) -> SourceRuntimeRegistry:
    key = id(store)
    registry = _source_runtime_registries.get(key)
    if registry is None:
        registry = SourceRuntimeRegistry(store)
        _source_runtime_registries[key] = registry
    return registry


async def record_source_outcome(
    identifier: str,
    status: SourceResultStatus,
    next_reset_at: datetime | None = None,
    *,
    store: EphemeralStore | None = None,
) -> None:
    await _runtime_registry(store or get_ephemeral_store()).record(
        identifier,
        status,
        next_reset_at,
    )


async def clear_source_outcomes(*, store: EphemeralStore | None = None) -> None:
    selected = store or get_ephemeral_store()
    registry = _source_runtime_registries.pop(id(selected), None)
    if registry is not None:
        await registry.clear()


async def source_availability(
    *,
    store: EphemeralStore | None = None,
) -> tuple[TrendSourceAvailability, ...]:
    registry = _runtime_registry(store or get_ephemeral_store())
    rss_enabled = sorted(
        (feed for feed in settings.rss_trends_allowlist if feed["enabled"]),
        key=lambda feed: str(feed["identifier"]),
    )
    definitions: list[tuple[str, str, str, bool, bool]] = [
        (
            "youtube-search",
            "YouTube Data API",
            "youtube",
            settings.youtube_trends_enabled,
            bool(settings.youtube_api_key),
        ),
        (
            "serpapi-google-trends",
            "Google Trends mediante SerpApi",
            "serpapi",
            settings.serpapi_trends_enabled,
            bool(settings.serpapi_api_key),
        ),
    ]
    definitions.extend(
        (
            f"rss-{feed['identifier']}",
            str(feed["public_name"]),
            "rss",
            settings.rss_trends_enabled,
            True,
        )
        for feed in rss_enabled
    )
    if not rss_enabled:
        definitions.append(
            (
                "rss-allowlist",
                "RSS/Atom permitidos",
                "rss",
                settings.rss_trends_enabled,
                False,
            )
        )
    available: list[TrendSourceAvailability] = []
    for identifier, public_name, source_type, enabled, configured in sorted(definitions):
        if not settings.trend_analysis_enabled or not enabled:
            status, reset = "disabled", None
        elif not configured:
            status, reset = "unconfigured", None
        else:
            runtime = await registry.get(identifier)
            status = runtime.status if runtime else "available"
            reset = runtime.next_reset_at if runtime else None
        available.append(
            TrendSourceAvailability(identifier, public_name, source_type, configured, status, reset)
        )
    return tuple(available)


def _source_cache(store: EphemeralStore) -> TrendSourceCache:
    """Reuse a cache/lock set for the configured store to coalesce concurrent refreshes."""

    key = id(store)
    cache = _source_caches.get(key)
    if cache is None:
        cache = TrendSourceCache(store)
        _source_caches[key] = cache
    return cache


def configured_trend_sources(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    store: EphemeralStore | None = None,
) -> tuple[TrendSource, ...]:
    """Construct only configured real sources; no fake provider crosses this boundary."""

    cache = _source_cache(store or get_ephemeral_store())
    # Quota reservations intentionally use a short, separate session rather
    # than the trend run transaction represented by ``db``.
    quota = TrendQuotaBudget(now=now or datetime.now(UTC))
    sources: list[TrendSource] = []
    if settings.youtube_trends_enabled and settings.youtube_api_key:
        sources.append(
            YouTubeTrendSource(
                api_key=settings.youtube_api_key,
                daily_budget=settings.youtube_search_daily_budget,
                cache_ttl_seconds=settings.youtube_cache_ttl_seconds,
                negative_cache_ttl_seconds=settings.trends_negative_cache_ttl_seconds,
                cache=cache,
                quota=quota,
                timeout_seconds=settings.trends_http_timeout_seconds,
                max_results=settings.trends_max_results_per_source,
            )
        )
    if settings.serpapi_trends_enabled and settings.serpapi_api_key:
        sources.append(
            SerpApiTrendSource(
                api_key=settings.serpapi_api_key,
                monthly_budget=settings.serpapi_monthly_budget,
                cache_ttl_seconds=settings.serpapi_cache_ttl_seconds,
                negative_cache_ttl_seconds=settings.trends_negative_cache_ttl_seconds,
                cache=cache,
                quota=quota,
                timeout_seconds=settings.trends_http_timeout_seconds,
                max_results=settings.trends_max_results_per_source,
            )
        )
    if settings.rss_trends_enabled:
        for entry in settings.rss_trends_allowlist:
            if not entry["enabled"]:
                continue
            sources.append(
                RssTrendSource(
                    feed=RssFeed(
                        identifier=str(entry["identifier"]),
                        public_name=str(entry["public_name"]),
                        feed_url=str(entry["feed_url"]),
                        regions=tuple(entry["regions"]),
                        categories=tuple(entry["categories"]),
                    ),
                    cache=cache,
                    cache_ttl_seconds=settings.rss_cache_ttl_seconds,
                    negative_cache_ttl_seconds=settings.trends_negative_cache_ttl_seconds,
                    timeout_seconds=settings.trends_http_timeout_seconds,
                    max_results=settings.trends_max_results_per_source,
                    max_response_bytes=settings.rss_max_response_bytes,
                    dns_timeout_seconds=settings.rss_dns_timeout_seconds,
                )
            )
    return tuple(sources)
