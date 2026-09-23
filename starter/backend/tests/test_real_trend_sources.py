from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from time import sleep

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import Settings
from app.core.ephemeral_store import MemoryEphemeralStore
from app.trends.cache import TrendSourceCache, cache_key
from app.trends.contracts import SourceFetchResult, SourceResultStatus
from app.trends.factory import (
    SOURCE_RUNTIME_TTL_SECONDS,
    SourceRuntimeRegistry,
    clear_source_outcomes,
    configured_trend_sources,
    record_source_outcome,
    source_availability,
)
from app.trends.models import TrendProviderBudget
from app.trends.quota import TrendQuotaBudget
from app.trends.real_sources import (
    PinnedRssRequest,
    PinnedRssResponse,
    RssFeed,
    RssResponseTooLarge,
    RssTrendSource,
    SerpApiTrendSource,
    YouTubeTrendSource,
    _read_pinned_body,
    resolve_pinned_rss_url,
    validate_rss_evidence_url,
    validate_rss_url,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)


def _cache(name: str) -> TrendSourceCache:
    return TrendSourceCache(MemoryEphemeralStore(prefix=f"trends-{name}", now=lambda: 0))


def test_cache_key_is_normalized_versioned_and_never_uses_a_secret() -> None:
    first = cache_key(
        source="youtube-search",
        adapter_version="real-sources-v1",
        region=" hn ",
        category=" Gastronomy ",
        query="Café  frío",
        public_parameters=("max-results=10", "published-day=2026-07-30"),
    )
    same = cache_key(
        source="youtube-search",
        adapter_version="real-sources-v1",
        region="HN",
        category="gastronomy",
        query="café frío",
        public_parameters=("published-day=2026-07-30", "max-results=10"),
    )
    changed = cache_key(
        source="youtube-search",
        adapter_version="real-sources-v1",
        region="HN",
        category="gastronomy",
        query="café frío",
        public_parameters=("max-results=5", "published-day=2026-07-30"),
    )
    assert first == same
    assert first != changed
    assert first.startswith("trends:source:")


async def _budget(db):
    await db.execute(delete(TrendProviderBudget))
    await db.commit()
    return _quota()


def _quota() -> TrendQuotaBudget:
    from tests.conftest import _TestingSessionFactory

    return TrendQuotaBudget(now=NOW, session_factory=_TestingSessionFactory)


def _youtube(db, handler, *, budget: int = 2) -> YouTubeTrendSource:
    return YouTubeTrendSource(
        api_key="test-key",
        daily_budget=budget,
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        cache=_cache("youtube"),
        quota=_quota(),
        now=lambda: NOW,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_youtube_maps_public_evidence_and_cache_does_not_debit_twice() -> None:
    from tests.conftest import _TestingSessionFactory

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.host == "www.googleapis.com"
        assert request.url.params["type"] == "video"
        assert request.url.params["safeSearch"] == "strict"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "AbCdEfGhI12"},
                        "snippet": {
                            "title": "<b>Tendencia local</b>",
                            "description": "<p>Resumen seguro</p>",
                            "publishedAt": "2026-07-29T10:00:00Z",
                        },
                    }
                ]
            },
        )

    async with _TestingSessionFactory() as db:
        await _budget(db)
        source = _youtube(db, handler)
        first = await source.fetch(region="HN", category="gastronomy")
        second = await source.fetch(region="HN", category="gastronomy")
        assert first.status == second.status == SourceResultStatus.SUCCESS
        assert calls == 1
        evidence = first.candidates[0].evidence[0]
        assert evidence.source_url == "https://www.youtube.com/watch?v=AbCdEfGhI12"
        assert "test-key" not in evidence.source_url
        ledger = await db.scalar(select(TrendProviderBudget).where(TrendProviderBudget.provider == "youtube"))
        assert ledger is not None and ledger.consumed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(403, json={"error": "quotaExceeded"}), SourceResultStatus.QUOTA_EXHAUSTED),
        (httpx.Response(429), SourceResultStatus.RATE_LIMITED),
        (httpx.Response(500), SourceResultStatus.ERROR),
        (httpx.Response(200, content=b"not json"), SourceResultStatus.INVALID),
    ],
)
async def test_youtube_provider_failures_are_safe(response, expected) -> None:
    from tests.conftest import _TestingSessionFactory

    async with _TestingSessionFactory() as db:
        await _budget(db)
        source = _youtube(db, lambda request: response)
        assert (await source.fetch(region="HN", category=None)).status == expected
        assert (await YouTubeTrendSource(
            api_key="", daily_budget=1, cache_ttl_seconds=1, negative_cache_ttl_seconds=1,
            cache=_cache("youtube-missing"), quota=_quota(),
        ).fetch(region="HN", category=None)).status == SourceResultStatus.ERROR


@pytest.mark.asyncio
async def test_youtube_budget_and_invalid_video_id_are_not_published() -> None:
    from tests.conftest import _TestingSessionFactory

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"id": {"videoId": "bad"}, "snippet": {"title": "x", "publishedAt": "2026-07-29T00:00:00Z"}}]},
        )

    async with _TestingSessionFactory() as db:
        await _budget(db)
        source = _youtube(db, handler, budget=1)
        assert (await source.fetch(region="HN", category="one")).status == SourceResultStatus.EMPTY
        assert (await source.fetch(region="HN", category="two")).status == SourceResultStatus.QUOTA_EXHAUSTED


@pytest.mark.asyncio
async def test_concurrent_real_source_requests_share_cache_lock_and_one_quota_debit() -> None:
    from tests.conftest import _TestingSessionFactory

    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "AbCdEfGhI12"},
                        "snippet": {
                            "title": "Solicitud concurrente",
                            "description": "",
                            "publishedAt": "2026-07-29T10:00:00Z",
                        },
                    }
                ]
            },
        )

    async with _TestingSessionFactory() as db:
        await _budget(db)
        source = _youtube(db, handler, budget=1)
        first, second = await asyncio.gather(
            source.fetch(region="HN", category="gastronomy"),
            source.fetch(region="HN", category="gastronomy"),
        )
        assert first.status == second.status == SourceResultStatus.SUCCESS
        assert calls == 1
        ledger = await db.scalar(
            select(TrendProviderBudget).where(TrendProviderBudget.provider == "youtube")
        )
        assert ledger is not None and ledger.consumed == 1


@pytest.mark.asyncio
async def test_slow_fetch_keeps_distributed_lease_until_cache_is_populated() -> None:
    from tests.conftest import _TestingSessionFactory

    calls = 0
    store = MemoryEphemeralStore(prefix="slow-distributed-lease")
    quota = _quota()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        del request
        calls += 1
        await asyncio.sleep(3.1)
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": {"videoId": "AbCdEfGhI12"},
                        "snippet": {
                            "title": "Lease lento",
                            "description": "",
                            "publishedAt": "2026-07-29T10:00:00Z",
                        },
                    }
                ]
            },
        )

    def source() -> YouTubeTrendSource:
        return YouTubeTrendSource(
            api_key="test-key",
            daily_budget=1,
            cache_ttl_seconds=300,
            negative_cache_ttl_seconds=30,
            cache=TrendSourceCache(store),
            quota=quota,
            now=lambda: NOW,
            timeout_seconds=5,
            transport=httpx.MockTransport(handler),
        )

    async with _TestingSessionFactory() as db:
        await _budget(db)
        first, second = await asyncio.gather(
            source().fetch(region="HN", category="gastronomy"),
            source().fetch(region="HN", category="gastronomy"),
        )
        assert first.status == second.status == SourceResultStatus.SUCCESS
        assert calls == 1
        ledger = await db.scalar(
            select(TrendProviderBudget).where(TrendProviderBudget.provider == "youtube")
        )
        assert ledger is not None and ledger.consumed == 1


def _serp(db, handler, *, budget: int = 2) -> SerpApiTrendSource:
    return SerpApiTrendSource(
        api_key="test-key",
        monthly_budget=budget,
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        cache=_cache("serp"),
        quota=_quota(),
        now=lambda: NOW,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_serpapi_maps_interpretable_google_trends_signals_and_caches() -> None:
    from tests.conftest import _TestingSessionFactory

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["engine"] == "google_trends"
        assert request.url.params["no_cache"] == "false"
        return httpx.Response(
            200,
            json={
                "related_queries": {
                    "rising": [
                        {
                            "query": "Café frío",
                            "value": "+4,500%",
                            "extracted_value": 4500,
                            "link": "https://trends.google.com/trends/explore?q=Caf%C3%A9+fr%C3%ADo",
                            "serpapi_link": "https://serpapi.example/private",
                        }
                    ],
                    "top": [],
                }
            },
        )

    async with _TestingSessionFactory() as db:
        await _budget(db)
        source = _serp(db, handler)
        result = await source.fetch(region="HN", category="gastronomy")
        assert result.status == SourceResultStatus.SUCCESS
        assert result.candidates[0].evidence[0].source_url.startswith("https://trends.google.com/")
        assert "test-key" not in result.candidates[0].evidence[0].source_url
        assert (await source.fetch(region="HN", category="gastronomy")).status == SourceResultStatus.SUCCESS
        assert calls == 1


@pytest.mark.asyncio
async def test_serpapi_real_rising_top_topics_and_global_geo_contract() -> None:
    from tests.conftest import _TestingSessionFactory

    def handler(request: httpx.Request) -> httpx.Response:
        assert "geo" not in request.url.params
        assert request.url.params["data_type"] == "RELATED_QUERIES"
        return httpx.Response(
            200,
            json={
                "related_queries": {
                    "rising": [
                        {"query": "Rising", "value": "+4,500%", "extracted_value": 4500},
                        {"query": "Breakout signal", "value": "Breakout"},
                    ],
                    "top": [{"query": "Top string", "value": "100"}],
                },
                "related_topics": {
                    "rising": [
                        {
                            "topic": {"value": "/m/01", "title": "Topic title", "type": "Topic"},
                            "value": "Breakout",
                            "extracted_value": 8700,
                            "link": "https://trends.google.com/trends/explore?q=topic",
                            "serpapi_link": "https://serpapi.example/private",
                        }
                    ],
                    "top": [{"topic": {"value": "/m/02"}, "value": "50"}],
                },
            },
        )

    async with _TestingSessionFactory() as db:
        await _budget(db)
        result = await _serp(db, handler).fetch(region="GLOBAL", category=None)
    assert result.status == SourceResultStatus.SUCCESS
    assert [candidate.title for candidate in result.candidates] == [
        "Rising",
        "Breakout signal",
        "Top string",
        "Topic title",
        "/m/02",
    ]
    assert all(0 <= candidate.evidence[0].confidence <= 1 for candidate in result.candidates)
    topic_evidence = result.candidates[3].evidence[0].source_url
    assert topic_evidence.startswith("https://trends.google.com/")
    assert "serpapi" not in topic_evidence


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, json={"error": "monthly credit limit"}), SourceResultStatus.QUOTA_EXHAUSTED),
        (httpx.Response(401), SourceResultStatus.ERROR),
        (httpx.Response(503), SourceResultStatus.ERROR),
        (
            httpx.Response(200, json={"related_queries": {"rising": [], "top": []}}),
            SourceResultStatus.EMPTY,
        ),
    ],
)
async def test_serpapi_safe_failures_and_empty_signals(response, expected) -> None:
    from tests.conftest import _TestingSessionFactory

    async with _TestingSessionFactory() as db:
        await _budget(db)
        assert (await _serp(db, lambda request: response).fetch(region="HN", category=None)).status == expected


@pytest.mark.asyncio
async def test_rss_and_atom_are_sanitized_and_ssrf_policy_rejects_private_hosts() -> None:
    def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]
    feed = RssFeed("news", "News", "https://feeds.example.com/rss", ("HN",), ())
    rss = b"""<?xml version='1.0'?><rss><channel><item><title>Hola <b>mundo</b></title><link>https://news.example.com/a</link><pubDate>Wed, 29 Jul 2026 10:00:00 +0000</pubDate><description>&lt;b&gt;Seguro&lt;/b&gt;</description></item></channel></rss>"""
    atom = b"""<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Atom</title><link href='https://news.example.com/b'/><updated>2026-07-29T10:00:00Z</updated><summary>&lt;i&gt;Texto&lt;/i&gt;</summary></entry></feed>"""

    def source(body: bytes) -> RssTrendSource:
        return RssTrendSource(
            feed=feed, cache=_cache(f"rss-{len(body)}"), cache_ttl_seconds=300,
            negative_cache_ttl_seconds=30, timeout_seconds=2, max_results=10,
            max_response_bytes=10_000, resolver=resolver,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body, headers={"content-type": "application/rss+xml"})),
        )

    rss_result = await source(rss).fetch(region="HN", category=None)
    atom_result = await source(atom).fetch(region="HN", category=None)
    assert rss_result.status == atom_result.status == SourceResultStatus.SUCCESS
    assert rss_result.candidates[0].summary == "Seguro"
    assert validate_rss_url(
        "https://feeds.example.com/rss", allowed_hosts={"feeds.example.com"}, resolver=lambda host: ["127.0.0.1"]
    ) is None
    assert validate_rss_url(
        "https://feeds.example.com/rss", allowed_hosts={"feeds.example.com"}, resolver=resolver
    ) == "https://feeds.example.com/rss"
    assert validate_rss_evidence_url("https://news.example.com/a#fragment") == (
        "https://news.example.com/a"
    )
    assert validate_rss_evidence_url("http://127.0.0.1/private") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(200, content=b"broken", headers={"content-type": "application/xml"}), SourceResultStatus.INVALID),
        (httpx.Response(200, content=b"<rss><channel/></rss>", headers={"content-type": "text/html"}), SourceResultStatus.INVALID),
        (httpx.Response(302, headers={"location": "https://outside.example/feed"}), SourceResultStatus.INVALID),
    ],
)
async def test_rss_rejects_malformed_content_and_unsafe_redirects(response, expected) -> None:
    feed = RssFeed("safe", "Safe", "https://feeds.example.com/rss", ("HN",), ())
    source = RssTrendSource(
        feed=feed, cache=_cache("rss-invalid"), cache_ttl_seconds=300, negative_cache_ttl_seconds=30,
        timeout_seconds=2, max_results=10, max_response_bytes=50, resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(lambda request: response),
    )
    assert (await source.fetch(region="HN", category=None)).status == expected


@pytest.mark.asyncio
async def test_rss_allows_only_same_allowlisted_redirect_and_enforces_response_limit() -> None:
    feed = RssFeed("safe", "Safe", "https://feeds.example.com/rss", ("HN",), ())
    calls = 0

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.path == "/rss":
            return httpx.Response(302, headers={"location": "/next"})
        return httpx.Response(
            200,
            content=(
                b"<rss><channel><item><title>Permitido</title>"
                b"<link>https://news.example.com/item</link>"
                b"<pubDate>Wed, 29 Jul 2026 10:00:00 +0000</pubDate>"
                b"</item></channel></rss>"
            ),
            headers={"content-type": "application/rss+xml"},
        )

    source = RssTrendSource(
        feed=feed,
        cache=_cache("rss-redirect-allowed"),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        max_results=10,
        max_response_bytes=10_000,
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(redirect_handler),
    )
    assert (await source.fetch(region="HN", category=None)).status == SourceResultStatus.SUCCESS
    assert calls == 2

    oversized = RssTrendSource(
        feed=feed,
        cache=_cache("rss-oversized"),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        max_results=10,
        max_response_bytes=10,
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=b"x" * 11, headers={"content-type": "application/xml"}
            )
        ),
    )
    assert (await oversized.fetch(region="HN", category=None)).status == SourceResultStatus.INVALID


@pytest.mark.asyncio
async def test_rss_timeout_and_cache_store_failure_are_safe() -> None:
    feed = RssFeed("safe", "Safe", "https://feeds.example.com/rss", ("HN",), ())
    timeout_source = RssTrendSource(
        feed=feed,
        cache=_cache("rss-timeout"),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        max_results=10,
        max_response_bytes=100,
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timed out"))
        ),
    )
    assert (await timeout_source.fetch(region="HN", category=None)).status == SourceResultStatus.TIMEOUT

    class BrokenStore:
        async def get(self, *, key: str) -> str | None:
            raise RuntimeError("redis unavailable")

        async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
            raise RuntimeError("redis unavailable")

    source = RssTrendSource(
        feed=feed,
        cache=TrendSourceCache(BrokenStore()),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        max_results=10,
        max_response_bytes=10_000,
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=(
                    b"<rss><channel><item><title>Cache fallback</title>"
                    b"<link>https://news.example.com/item</link>"
                    b"<pubDate>Wed, 29 Jul 2026 10:00:00 +0000</pubDate>"
                    b"</item></channel></rss>"
                ),
                headers={"content-type": "application/rss+xml"},
            )
        ),
    )
    assert (await source.fetch(region="HN", category=None)).status == SourceResultStatus.SUCCESS


@pytest.mark.asyncio
async def test_rss_pins_validated_dns_address_and_rejects_rebinding_or_private_ips() -> None:
    feed = RssFeed("safe", "Safe", "https://feeds.example.com/rss", ("HN",), ())

    class RecordingConnector:
        def __init__(self) -> None:
            self.requests: list[PinnedRssRequest] = []

        async def fetch(self, request: PinnedRssRequest, *, timeout_seconds: float) -> PinnedRssResponse:
            del timeout_seconds
            self.requests.append(request)
            return PinnedRssResponse(302, {"location": "/redirected"}, b"")

    resolutions = iter([["93.184.216.34"], ["127.0.0.1"]])
    connector = RecordingConnector()
    source = RssTrendSource(
        feed=feed,
        cache=_cache("rss-pinned"),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        dns_timeout_seconds=0.1,
        max_results=10,
        max_response_bytes=10_000,
        resolver=lambda host: next(resolutions),
        connector=connector,
    )
    assert (await source.fetch(region="HN", category=None)).status == SourceResultStatus.INVALID
    assert len(connector.requests) == 1
    assert connector.requests[0].address == "93.184.216.34"
    assert connector.requests[0].host == "feeds.example.com"

    for private in ("::1", "fe80::1", "::ffff:127.0.0.1"):
        assert validate_rss_url(
            "https://feeds.example.com/rss",
            allowed_hosts={"feeds.example.com"},
            resolver=lambda host, address=private: [address],
        ) is None


@pytest.mark.asyncio
async def test_rss_dns_resolution_is_bounded_and_off_event_loop() -> None:
    def slow_resolver(host: str) -> list[str]:
        del host
        sleep(0.05)
        return ["93.184.216.34"]

    resolved = await resolve_pinned_rss_url(
        "https://feeds.example.com/rss",
        allowed_hosts={"feeds.example.com"},
        resolver=slow_resolver,
        timeout_seconds=0.001,
        max_response_bytes=100,
    )
    assert resolved is None


@pytest.mark.asyncio
async def test_rss_evidence_links_never_trigger_dns_resolution() -> None:
    calls: list[str] = []

    def resolver(host: str) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    items = "".join(
        (
            f"<item><title>Item {index}</title>"
            f"<link>https://news-{index}.example.com/story</link>"
            "<pubDate>Wed, 29 Jul 2026 10:00:00 +0000</pubDate></item>"
        )
        for index in range(25)
    )
    source = RssTrendSource(
        feed=RssFeed(
            "dns-count",
            "DNS Count",
            "https://feeds.example.com/rss",
            ("HN",),
            (),
        ),
        cache=_cache("rss-dns-count"),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        max_results=25,
        max_response_bytes=100_000,
        resolver=resolver,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=f"<rss><channel>{items}</channel></rss>".encode(),
                headers={"content-type": "application/rss+xml"},
            )
        ),
    )
    result = await source.fetch(region="HN", category=None)
    assert result.status == SourceResultStatus.SUCCESS
    assert len(result.candidates) == 25
    assert calls == ["feeds.example.com"]


@pytest.mark.asyncio
async def test_rss_unknown_length_body_reads_all_fragments_and_enforces_limit() -> None:
    class FragmentedReader:
        def __init__(self, fragments: list[bytes]) -> None:
            self.fragments = fragments

        async def read(self, maximum: int) -> bytes:
            del maximum
            return self.fragments.pop(0) if self.fragments else b""

    complete = await _read_pinned_body(
        FragmentedReader([b"<rss>", b"<channel/>", b"</rss>", b""]),  # type: ignore[arg-type]
        headers={},
        maximum=100,
        timeout_seconds=1,
    )
    assert complete == b"<rss><channel/></rss>"
    with pytest.raises(RssResponseTooLarge):
        await _read_pinned_body(
            FragmentedReader([b"1234", b"5678", b""]),  # type: ignore[arg-type]
            headers={},
            maximum=7,
            timeout_seconds=1,
        )


@pytest.mark.asyncio
async def test_distributed_cache_lease_coalesces_instances_and_releases_only_owner() -> None:
    clock = [0.0]
    store = MemoryEphemeralStore(prefix="lease", now=lambda: clock[0])
    first, second = TrendSourceCache(store), TrendSourceCache(store)
    key = "trends:source:lease-test"
    calls = 0

    async def fetch() -> SourceFetchResult:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        result = SourceFetchResult(SourceResultStatus.EMPTY)
        await first.set(key, result, ttl_seconds=30)
        return result

    one, two = await asyncio.gather(first.coalesce(key, fetch), second.coalesce(key, fetch))
    assert one.status == two.status == SourceResultStatus.EMPTY
    assert calls == 1
    assert first._locks == second._locks == {}
    assert first._lock_users == second._lock_users == {}

    assert await store.acquire_lease(key="lease:owner", token="owner", ttl_seconds=3)
    await store.release_lease(key="lease:owner", token="other")
    assert await store.acquire_lease(key="lease:owner", token="next", ttl_seconds=3) is False
    clock[0] = 4.0
    assert await store.acquire_lease(key="lease:owner", token="next", ttl_seconds=3)


@pytest.mark.asyncio
async def test_trend_source_configuration_is_bounded_and_honest(monkeypatch) -> None:
    invalid = {"RSS_TRENDS_ENABLED": "true", "RSS_TRENDS_ALLOWLIST": "[]"}
    Settings(invalid).validate_runtime_configuration()
    Settings({"YOUTUBE_TRENDS_ENABLED": "true", "YOUTUBE_API_KEY": ""}).validate_runtime_configuration()
    Settings({"SERPAPI_TRENDS_ENABLED": "true", "SERPAPI_API_KEY": ""}).validate_runtime_configuration()
    with pytest.raises(RuntimeError, match="YOUTUBE_SEARCH_DAILY_BUDGET"):
        Settings({"YOUTUBE_SEARCH_DAILY_BUDGET": "10001"})
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "youtube_trends_enabled", True)
    monkeypatch.setattr(settings, "youtube_api_key", "")
    assert next(
        item
        for item in await source_availability()
        if item.identifier == "youtube-search"
    ).status == "unconfigured"
    monkeypatch.setattr(settings, "rss_trends_enabled", True)
    monkeypatch.setattr(
        settings,
        "rss_trends_allowlist",
        ({"identifier": "safe", "public_name": "Safe", "feed_url": "https://feeds.example.com/rss", "regions": ("HN",), "categories": (), "enabled": True},),
    )
    sources = configured_trend_sources(None)  # type: ignore[arg-type]
    assert [source.identifier for source in sources] == ["rss-safe"]


@pytest.mark.asyncio
async def test_authenticated_source_availability_is_safe_and_keeps_per_source_quota(client, monkeypatch) -> None:
    from app.core.config import settings

    await clear_source_outcomes()
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "youtube_trends_enabled", True)
    monkeypatch.setattr(settings, "youtube_api_key", "test-key")
    monkeypatch.setattr(settings, "serpapi_trends_enabled", True)
    monkeypatch.setattr(settings, "serpapi_api_key", "test-key")
    future_reset = datetime.now(UTC) + timedelta(days=1)
    await record_source_outcome(
        "serpapi-google-trends",
        SourceResultStatus.QUOTA_EXHAUSTED,
        future_reset,
    )
    try:
        response = await client.get("/api/v1/trends/sources", headers={"X-Workspace-Id": "ws_test_001"})
        assert response.status_code == 200
        sources = {item["identifier"]: item for item in response.json()["sources"]}
        assert sources["youtube-search"]["status"] == "available"
        assert sources["serpapi-google-trends"]["status"] == "quota_exhausted"
        assert sources["serpapi-google-trends"]["next_reset_at"]
        assert "test-key" not in response.text
    finally:
        await clear_source_outcomes()


@pytest.mark.asyncio
async def test_rss_feed_health_is_per_identifier_order_independent_and_empty_is_healthy(
    monkeypatch,
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "rss_trends_enabled", True)
    monkeypatch.setattr(
        settings,
        "rss_trends_allowlist",
        (
            {
                "identifier": "b",
                "public_name": "Feed B",
                "feed_url": "https://b.example.com/rss",
                "regions": ("HN",),
                "categories": (),
                "enabled": True,
            },
            {
                "identifier": "a",
                "public_name": "Feed A",
                "feed_url": "https://a.example.com/rss",
                "regions": ("HN",),
                "categories": (),
                "enabled": True,
            },
        ),
    )

    snapshots = []
    observed_now = datetime.now(UTC)
    for index, outcomes in enumerate(
        (
            (
                ("rss-a", SourceResultStatus.EMPTY),
                ("rss-b", SourceResultStatus.INVALID),
            ),
            (
                ("rss-b", SourceResultStatus.INVALID),
                ("rss-a", SourceResultStatus.EMPTY),
            ),
        )
    ):
        store = MemoryEphemeralStore(prefix=f"feed-order-{index}")
        registry = SourceRuntimeRegistry(store, now=lambda: observed_now)
        for identifier, status in outcomes:
            await registry.record(identifier, status)
        snapshots.append(
            [
                (source.identifier, source.status)
                for source in await source_availability(store=store)
                if source.source_type == "rss"
            ]
        )
    assert snapshots[0] == snapshots[1] == [
        ("rss-a", "available"),
        ("rss-b", "degraded"),
    ]


@pytest.mark.asyncio
async def test_source_runtime_is_shared_expires_recovers_and_falls_back_locally() -> None:
    clock = [0.0]
    wall_clock = [NOW]
    store = MemoryEphemeralStore(prefix="shared-runtime", now=lambda: clock[0])
    first = SourceRuntimeRegistry(store, now=lambda: wall_clock[0])
    second = SourceRuntimeRegistry(store, now=lambda: wall_clock[0])

    await first.record(
        "serpapi-google-trends",
        SourceResultStatus.QUOTA_EXHAUSTED,
        NOW + timedelta(minutes=10),
    )
    shared = await second.get("serpapi-google-trends")
    assert shared is not None
    assert shared.status == "quota_exhausted"
    assert shared.next_reset_at == NOW + timedelta(minutes=10)

    await first.record("serpapi-google-trends", SourceResultStatus.SUCCESS)
    recovered = await second.get("serpapi-google-trends")
    assert recovered is not None
    assert recovered.status == "available"
    assert recovered.next_reset_at is None

    await first.record(
        "youtube-search",
        SourceResultStatus.QUOTA_EXHAUSTED,
        NOW + timedelta(seconds=1),
    )
    clock[0] = 2
    wall_clock[0] = NOW + timedelta(seconds=2)
    expired_quota = await second.get("youtube-search")
    assert expired_quota is not None
    assert expired_quota.status == "available"
    assert expired_quota.next_reset_at is None

    await first.record("rss-a", SourceResultStatus.INVALID)
    clock[0] = SOURCE_RUNTIME_TTL_SECONDS + 3
    wall_clock[0] = NOW + timedelta(seconds=SOURCE_RUNTIME_TTL_SECONDS + 3)
    assert await second.get("rss-a") is None

    class BrokenStore:
        async def get(self, *, key: str) -> str | None:
            raise RuntimeError(key)

        async def set(
            self,
            *,
            key: str,
            value: str,
            ttl_seconds: int | None = None,
        ) -> None:
            raise RuntimeError((key, value, ttl_seconds))

    fallback = SourceRuntimeRegistry(BrokenStore(), now=lambda: NOW)  # type: ignore[arg-type]
    await fallback.record("rss-fallback", SourceResultStatus.TIMEOUT)
    local = await fallback.get("rss-fallback")
    assert local is not None and local.status == "degraded"


class _CountingRssTrendSource(RssTrendSource):
    """Count fetch calls so a skipped source is provably never consulted."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.fetches = 0

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        self.fetches += 1
        return await super().fetch(region=region, category=category)


def _forbidden_resolver(host: str) -> list[str]:
    raise AssertionError(f"DNS para una fuente no aplicable: {host}")


class _ForbiddenConnector:
    def __init__(self) -> None:
        self.requests: list[PinnedRssRequest] = []

    async def fetch(self, request: PinnedRssRequest, *, timeout_seconds: float) -> PinnedRssResponse:
        del timeout_seconds
        self.requests.append(request)
        raise AssertionError(f"HTTP para una fuente no aplicable: {request.host}")


def _allowlist_entry(identifier: str, *, regions: tuple[str, ...], categories: tuple[str, ...]):
    return {
        "identifier": identifier,
        "public_name": f"Feed {identifier}",
        "feed_url": f"https://{identifier}.example.com/rss",
        "regions": regions,
        "categories": categories,
        "enabled": True,
    }


def _scoped_rss(
    identifier: str,
    *,
    regions: tuple[str, ...],
    categories: tuple[str, ...],
    resolver=_forbidden_resolver,
    connector=None,
    transport=None,
) -> _CountingRssTrendSource:
    entry = _allowlist_entry(identifier, regions=regions, categories=categories)
    return _CountingRssTrendSource(
        feed=RssFeed(
            identifier,
            str(entry["public_name"]),
            str(entry["feed_url"]),
            regions,
            categories,
        ),
        cache=_cache(f"scope-{identifier}"),
        cache_ttl_seconds=300,
        negative_cache_ttl_seconds=30,
        timeout_seconds=2,
        max_results=10,
        max_response_bytes=10_000,
        resolver=resolver,
        connector=connector if transport is None else None,
        transport=transport,
    )


async def _refresh_recording_outcomes(
    db,
    source,
    *,
    store,
    monkeypatch,
    region,
    category,
    capability_registry=None,
):
    """Run a refresh while capturing every runtime outcome it records."""

    from app.trends.service import TrendService

    recorded: list[tuple[str, SourceResultStatus]] = []

    async def _record(identifier, status, next_reset_at=None):
        recorded.append((identifier, status))
        await record_source_outcome(identifier, status, next_reset_at, store=store)

    monkeypatch.setattr("app.trends.service.record_source_outcome", _record)
    run = await TrendService(db, (source,), capability_registry=capability_registry).refresh(
        workspace_id="ws_test_001", region=region, category=category
    )
    return run, recorded


async def _rss_status(store, identifier: str) -> str:
    return next(
        item.status
        for item in await source_availability(store=store)
        if item.identifier == identifier
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("region", ["BR", "GLOBAL"])
async def test_region_outside_the_declared_scope_is_skipped_and_is_not_a_provider_failure(
    region, monkeypatch
) -> None:
    from app.core.capabilities import (
        Capability,
        CapabilityOutcome,
        get_runtime_capability_registry,
    )
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    identifier = f"hn-only-{region.lower()}"
    dns_requests: list[str] = []

    def resolver(host: str) -> list[str]:
        dns_requests.append(host)
        raise AssertionError(f"DNS para una fuente no aplicable: {host}")

    connector = _ForbiddenConnector()
    source = _scoped_rss(
        identifier,
        regions=("HN",),
        categories=(),
        resolver=resolver,
        connector=connector,
    )
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "rss_trends_enabled", True)
    monkeypatch.setattr(
        settings,
        "rss_trends_allowlist",
        (_allowlist_entry(identifier, regions=("HN",), categories=()),),
    )
    store = MemoryEphemeralStore(prefix=f"skip-region-{identifier}")
    registry = get_runtime_capability_registry()
    registry._outcome_store.clear(Capability.TREND_ANALYSIS)
    try:
        prior_reset = NOW + timedelta(hours=1)
        await registry.record_outcome_for(
            Capability.TREND_ANALYSIS,
            CapabilityOutcome.QUOTA_EXHAUSTED,
            prior_reset,
        )
        capability_calls: list[
            tuple[Capability, CapabilityOutcome, datetime | None]
        ] = []
        original_record_outcome_for = registry.record_outcome_for

        async def _record_capability(
            capability: Capability,
            outcome: CapabilityOutcome,
            next_reset_at: datetime | None = None,
        ) -> None:
            capability_calls.append((capability, outcome, next_reset_at))
            await original_record_outcome_for(capability, outcome, next_reset_at)

        monkeypatch.setattr(registry, "record_outcome_for", _record_capability)
        await record_source_outcome(source.identifier, SourceResultStatus.INVALID, store=store)
        assert await _rss_status(store, source.identifier) == "degraded"

        async with _TestingSessionFactory() as db:
            run, recorded = await _refresh_recording_outcomes(
                db,
                source,
                store=store,
                monkeypatch=monkeypatch,
                region=region,
                category=None,
                capability_registry=registry,
            )

        assert source.fetches == 0
        assert dns_requests == []
        assert connector.requests == []
        assert recorded == []
        assert capability_calls == []
        assert json.loads(run.sources_attempted) == []
        assert json.loads(run.sources_failed) == []
        assert json.loads(run.sources_succeeded) == []
        assert await _rss_status(store, source.identifier) == "degraded"
        assert (
            registry._outcome_store.get(Capability.TREND_ANALYSIS)
            == CapabilityOutcome.QUOTA_EXHAUSTED
        )
        assert (
            registry._outcome_store.get_next_reset_at(Capability.TREND_ANALYSIS)
            == prior_reset
        )
    finally:
        await clear_source_outcomes(store=store)
        registry._outcome_store.clear(Capability.TREND_ANALYSIS)


@pytest.mark.asyncio
async def test_applicable_rss_failure_records_provider_outcome(monkeypatch) -> None:
    from app.core.capabilities import (
        Capability,
        CapabilityOutcome,
        CapabilityRegistry,
        MemoryCapabilityOutcomeStore,
    )
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    source = _scoped_rss(
        "hn-failing",
        regions=("HN",),
        categories=(),
        resolver=lambda host: ["93.184.216.34"],
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    store = MemoryEphemeralStore(prefix="applicable-rss-failure")
    registry = CapabilityRegistry(outcome_store=MemoryCapabilityOutcomeStore())
    capability_calls: list[tuple[Capability, CapabilityOutcome, datetime | None]] = []
    original_record_outcome_for = registry.record_outcome_for

    async def _record_capability(
        capability: Capability,
        outcome: CapabilityOutcome,
        next_reset_at: datetime | None = None,
    ) -> None:
        capability_calls.append((capability, outcome, next_reset_at))
        await original_record_outcome_for(capability, outcome, next_reset_at)

    monkeypatch.setattr(registry, "record_outcome_for", _record_capability)
    try:
        async with _TestingSessionFactory() as db:
            run, recorded = await _refresh_recording_outcomes(
                db,
                source,
                store=store,
                monkeypatch=monkeypatch,
                region="HN",
                category=None,
                capability_registry=registry,
            )

        assert source.fetches == 1
        assert json.loads(run.sources_attempted) == [source.identifier]
        assert json.loads(run.sources_succeeded) == []
        assert json.loads(run.sources_failed) == [source.identifier]
        assert recorded == [(source.identifier, SourceResultStatus.ERROR)]
        assert capability_calls == [
            (Capability.TREND_ANALYSIS, CapabilityOutcome.PROVIDER_ERROR, None)
        ]
    finally:
        await clear_source_outcomes(store=store)


@pytest.mark.asyncio
async def test_category_outside_the_declared_scope_never_becomes_a_healthy_empty(
    monkeypatch,
) -> None:
    from app.core.config import settings
    from tests.conftest import _TestingSessionFactory

    identifier = "news-only"
    monkeypatch.setattr(settings, "trend_analysis_enabled", True)
    monkeypatch.setattr(settings, "rss_trends_enabled", True)
    monkeypatch.setattr(
        settings,
        "rss_trends_allowlist",
        (_allowlist_entry(identifier, regions=("HN",), categories=("news",)),),
    )
    store = MemoryEphemeralStore(prefix="skip-category")
    skipped = _scoped_rss(
        identifier,
        regions=("HN",),
        categories=("news",),
        connector=_ForbiddenConnector(),
    )
    try:
        await record_source_outcome(skipped.identifier, SourceResultStatus.INVALID, store=store)

        async with _TestingSessionFactory() as db:
            run, recorded = await _refresh_recording_outcomes(
                db,
                skipped,
                store=store,
                monkeypatch=monkeypatch,
                region="HN",
                category="gastronomy",
            )

        assert skipped.fetches == 0
        assert recorded == []
        assert json.loads(run.sources_attempted) == []
        assert await _rss_status(store, skipped.identifier) == "degraded"

        queried = _scoped_rss(
            identifier,
            regions=("HN",),
            categories=("news",),
            resolver=lambda host: ["93.184.216.34"],
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    content=b"<?xml version='1.0'?><rss><channel></channel></rss>",
                    headers={"content-type": "application/rss+xml"},
                )
            ),
        )
        async with _TestingSessionFactory() as db:
            queried_run, queried_recorded = await _refresh_recording_outcomes(
                db,
                queried,
                store=store,
                monkeypatch=monkeypatch,
                region="HN",
                category="news",
            )

        assert queried.fetches == 1
        assert queried_recorded == [(queried.identifier, SourceResultStatus.EMPTY)]
        assert json.loads(queried_run.sources_attempted) == [queried.identifier]
        assert await _rss_status(store, queried.identifier) == "available"
    finally:
        await clear_source_outcomes(store=store)


def _runtime_payload(status: str, observed_at: datetime) -> str:
    return json.dumps(
        {"status": status, "next_reset_at": None, "observed_at": observed_at.isoformat()}
    )


class _SharedRuntimeStore:
    """A shared store whose reads keep working while its writes fail."""

    def __init__(self, payload: str | None = None, *, writable: bool = False) -> None:
        self.payload, self.writable = payload, writable

    async def get(self, *, key: str) -> str | None:
        del key
        return self.payload

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        del key, ttl_seconds
        if not self.writable:
            raise RuntimeError("shared write failed")
        self.payload = value

    async def delete(self, *, key: str) -> None:
        del key
        self.payload = None


@pytest.mark.asyncio
async def test_source_runtime_get_returns_the_most_recent_observation() -> None:
    stale_shared = _SharedRuntimeStore(_runtime_payload("degraded", NOW - timedelta(minutes=1)))
    registry = SourceRuntimeRegistry(stale_shared, now=lambda: NOW)  # type: ignore[arg-type]
    await registry.record("rss-recency", SourceResultStatus.SUCCESS)
    # The shared write failed, so the store still returns the old degraded
    # observation; the newer local success is the truth about this source.
    assert stale_shared.payload == _runtime_payload("degraded", NOW - timedelta(minutes=1))
    fresh_local = await registry.get("rss-recency")
    assert fresh_local is not None
    assert fresh_local.status == "available"
    assert fresh_local.observed_at == NOW

    clock = [NOW - timedelta(minutes=1)]
    inverse = SourceRuntimeRegistry(
        _SharedRuntimeStore(),  # type: ignore[arg-type]
        now=lambda: clock[0],
    )
    await inverse.record("rss-recency", SourceResultStatus.SUCCESS)
    clock[0] = NOW
    inverse.store.payload = _runtime_payload("degraded", NOW - timedelta(seconds=10))  # type: ignore[attr-defined]
    fresh_shared = await inverse.get("rss-recency")
    assert fresh_shared is not None
    assert fresh_shared.status == "degraded"
    assert fresh_shared.observed_at == NOW - timedelta(seconds=10)


@pytest.mark.asyncio
async def test_rss_allowlist_identifiers_are_normalized_before_duplicate_detection() -> None:
    def allowlist(*identifiers: str) -> dict[str, str]:
        return {
            "RSS_TRENDS_ALLOWLIST": json.dumps(
                [
                    {
                        "identifier": identifier,
                        "public_name": "Feed",
                        "feed_url": "https://feeds.example.com/rss",
                        "regions": ["HN"],
                        "categories": [],
                        "enabled": True,
                    }
                    for identifier in identifiers
                ]
            )
        }

    for invalid in (
        allowlist("feed-a", " feed-a "),
        allowlist(""),
        allowlist("   "),
        allowlist("BBC-News"),
        allowlist("bbc news"),
        allowlist("trends:source:bbc"),
        allowlist("bbc\nnews"),
        allowlist("b" * 64),
        allowlist("-bbc"),
    ):
        with pytest.raises(RuntimeError, match="RSS_TRENDS_ALLOWLIST"):
            Settings(invalid)

    parsed = Settings(allowlist(" bbc-news ")).rss_trends_allowlist
    assert [feed["identifier"] for feed in parsed] == ["bbc-news"]
    assert [feed["identifier"] for feed in Settings(allowlist("b" * 63)).rss_trends_allowlist] == [
        "b" * 63
    ]
