from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
import ssl
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.trends.cache import CacheLeaseBusy, TrendSourceCache, cache_key
from app.trends.contracts import (
    SourceCandidate,
    SourceEvidence,
    SourceFetchResult,
    SourceResultStatus,
)
from app.trends.quota import BudgetPeriod, TrendQuotaBudget

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
ADAPTER_VERSION = "real-sources-v1"
HTTP_LIMITS = httpx.Limits(max_connections=5, max_keepalive_connections=2)
RSS_MAX_HEADER_BYTES = 16_384


def _language(region: str) -> str:
    return {"HN": "es", "BR": "pt"}.get(region.upper(), "en")


def _query(category: str | None) -> str:
    return category.replace("_", " ").strip() if category else "trending topics"


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo and parsed.utcoffset() is not None else None


class _TextOnly(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_text(value: object, *, limit: int = 800) -> str:
    if not isinstance(value, str):
        return ""
    parser = _TextOnly()
    parser.feed(value)
    parser.close()
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()[:limit]


def _source_result_status(response: httpx.Response, payload: object) -> SourceResultStatus:
    if response.status_code == 429:
        return SourceResultStatus.RATE_LIMITED
    if response.status_code == 403 and isinstance(payload, dict):
        reasons = str(payload.get("error", "")).lower()
        if "quota" in reasons or "daily" in reasons:
            return SourceResultStatus.QUOTA_EXHAUSTED
    if response.status_code >= 400:
        return SourceResultStatus.ERROR
    return SourceResultStatus.SUCCESS


class _HttpTrendSource:
    cache_ttl_seconds: int
    identifier: str

    def __init__(
        self,
        *,
        cache: TrendSourceCache,
        quota: TrendQuotaBudget,
        now: Callable[[], datetime],
        timeout_seconds: float,
        max_results: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cache = cache
        self.quota = quota
        self.now = now
        self.timeout_seconds = timeout_seconds
        self.max_results = max_results
        self.transport = transport

    async def _cached(
        self,
        *,
        region: str,
        category: str | None,
        query: str,
        public_parameters: tuple[str, ...],
        fetch: Callable[[], Awaitable[SourceFetchResult]],
    ) -> SourceFetchResult:
        key = cache_key(
            source=self.identifier,
            adapter_version=ADAPTER_VERSION,
            region=region,
            category=category,
            query=query,
            public_parameters=public_parameters,
        )
        cached = await self.cache.get(key)
        if cached is not None:
            return cached

        async def fresh() -> SourceFetchResult:
            result = await fetch()
            if result.status in {SourceResultStatus.SUCCESS, SourceResultStatus.EMPTY}:
                await self.cache.set(
                    key,
                    result,
                    ttl_seconds=(
                        self.cache_ttl_seconds
                        if result.status == SourceResultStatus.SUCCESS
                        else self.negative_cache_ttl_seconds
                    ),
                )
            return result

        return await self.cache.coalesce(
            key,
            fresh,
            operation_deadline_seconds=self.timeout_seconds,
        )


class YouTubeTrendSource(_HttpTrendSource):
    identifier = "youtube-search"
    public_name = "YouTube Data API"
    source_type = "youtube"
    supported_regions = ("GLOBAL", "HN", "BR")
    supported_categories: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        api_key: str,
        daily_budget: int,
        cache_ttl_seconds: int,
        negative_cache_ttl_seconds: int,
        cache: TrendSourceCache,
        quota: TrendQuotaBudget,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        timeout_seconds: float = 10,
        max_results: int = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            cache=cache, quota=quota, now=now, timeout_seconds=timeout_seconds,
            max_results=max_results, transport=transport,
        )
        self.api_key, self.daily_budget = api_key, daily_budget
        self.cache_ttl_seconds = cache_ttl_seconds
        self.negative_cache_ttl_seconds = negative_cache_ttl_seconds
        self.available = bool(api_key)

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        if not self.api_key:
            return SourceFetchResult(SourceResultStatus.ERROR)
        query = _query(category)
        try:
            return await self._cached(
                region=region, category=category, query=query,
                public_parameters=(
                    f"max-results={self.max_results}",
                    f"published-day={self.now().astimezone(UTC).date().isoformat()}",
                ),
                fetch=lambda: self._fetch_network(region=region, category=category, query=query),
            )
        except (CacheLeaseBusy, TimeoutError):
            return SourceFetchResult(SourceResultStatus.TIMEOUT)

    async def _fetch_network(self, *, region: str, category: str | None, query: str) -> SourceFetchResult:
        reservation = await self.quota.reserve(
            provider="youtube", operation="search.list", period=BudgetPeriod.DAY,
            budget=self.daily_budget,
        )
        if not reservation.granted:
            return SourceFetchResult(
                SourceResultStatus.QUOTA_EXHAUSTED, next_reset_at=reservation.next_reset_at
            )
        now = self.now().astimezone(UTC)
        params: dict[str, object] = {
            "key": self.api_key,
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": self.max_results,
            "publishedAfter": (now - timedelta(days=7)).isoformat().replace("+00:00", "Z"),
            "relevanceLanguage": _language(region),
            "safeSearch": "strict",
            "order": "relevance",
        }
        if region != "GLOBAL":
            params["regionCode"] = region
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                limits=HTTP_LIMITS,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.get(YOUTUBE_SEARCH_URL, params=params)
            if response.status_code >= 400:
                try:
                    error_payload = response.json()
                except ValueError:
                    error_payload = {}
                return SourceFetchResult(_source_result_status(response, error_payload))
            try:
                payload = response.json()
            except ValueError:
                return SourceFetchResult(SourceResultStatus.INVALID)
        except httpx.TimeoutException:
            return SourceFetchResult(SourceResultStatus.TIMEOUT)
        except httpx.HTTPError:
            return SourceFetchResult(SourceResultStatus.ERROR)
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return SourceFetchResult(SourceResultStatus.INVALID)
        candidates: list[SourceCandidate] = []
        for item in payload["items"][: self.max_results]:
            if not isinstance(item, dict):
                continue
            video_id = item.get("id", {}).get("videoId") if isinstance(item.get("id"), dict) else None
            snippet = item.get("snippet")
            if not isinstance(video_id, str) or not YOUTUBE_ID.fullmatch(video_id) or not isinstance(snippet, dict):
                continue
            title = clean_text(snippet.get("title"), limit=240)
            observed = _timestamp(snippet.get("publishedAt"))
            if not title or observed is None:
                continue
            candidates.append(
                SourceCandidate(
                    title=title,
                    summary=clean_text(snippet.get("description")),
                    region=region,
                    category=category,
                    observed_at=observed,
                    evidence=(
                        SourceEvidence(
                            source_url=f"https://www.youtube.com/watch?v={video_id}",
                            observed_at=observed,
                            region=region,
                            confidence=0.65,
                        ),
                    ),
                )
            )
        return SourceFetchResult(
            SourceResultStatus.SUCCESS if candidates else SourceResultStatus.EMPTY,
            tuple(candidates),
        )


class SerpApiTrendSource(_HttpTrendSource):
    identifier = "serpapi-google-trends"
    public_name = "SerpApi Google Trends"
    source_type = "serpapi"
    supported_regions = ("GLOBAL", "HN", "BR")
    supported_categories: tuple[str, ...] = ()

    def __init__(
        self,
        *,
        api_key: str,
        monthly_budget: int,
        cache_ttl_seconds: int,
        negative_cache_ttl_seconds: int,
        cache: TrendSourceCache,
        quota: TrendQuotaBudget,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        timeout_seconds: float = 10,
        max_results: int = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            cache=cache, quota=quota, now=now, timeout_seconds=timeout_seconds,
            max_results=max_results, transport=transport,
        )
        self.api_key, self.monthly_budget = api_key, monthly_budget
        self.cache_ttl_seconds = cache_ttl_seconds
        self.negative_cache_ttl_seconds = negative_cache_ttl_seconds
        self.available = bool(api_key)

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        if not self.api_key:
            return SourceFetchResult(SourceResultStatus.ERROR)
        query = _query(category)
        try:
            return await self._cached(
                region=region, category=category, query=query,
                public_parameters=(
                    f"max-results={self.max_results}",
                    f"observed-day={self.now().astimezone(UTC).date().isoformat()}",
                    "data-type=related-queries",
                ),
                fetch=lambda: self._fetch_network(region=region, category=category, query=query),
            )
        except (CacheLeaseBusy, TimeoutError):
            return SourceFetchResult(SourceResultStatus.TIMEOUT)

    async def _fetch_network(self, *, region: str, category: str | None, query: str) -> SourceFetchResult:
        reservation = await self.quota.reserve(
            provider="serpapi", operation="google_trends", period=BudgetPeriod.MONTH,
            budget=self.monthly_budget,
        )
        if not reservation.granted:
            return SourceFetchResult(
                SourceResultStatus.QUOTA_EXHAUSTED, next_reset_at=reservation.next_reset_at
            )
        params = {
            "api_key": self.api_key,
            "engine": "google_trends",
            "q": query,
            "hl": _language(region),
            "date": "now 7-d",
            "data_type": "RELATED_QUERIES",
            "no_cache": "false",
            "output": "json",
        }
        if region != "GLOBAL":
            params["geo"] = region
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                limits=HTTP_LIMITS,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.get(SERPAPI_SEARCH_URL, params=params)
            if response.status_code >= 400:
                return SourceFetchResult(_source_result_status(response, {}))
            try:
                payload = response.json()
            except ValueError:
                return SourceFetchResult(SourceResultStatus.INVALID)
        except httpx.TimeoutException:
            return SourceFetchResult(SourceResultStatus.TIMEOUT)
        except httpx.HTTPError:
            return SourceFetchResult(SourceResultStatus.ERROR)
        if isinstance(payload, dict) and isinstance(payload.get("error"), str):
            error = payload["error"].casefold()
            return SourceFetchResult(
                SourceResultStatus.QUOTA_EXHAUSTED
                if any(marker in error for marker in ("quota", "credit", "limit"))
                else SourceResultStatus.ERROR
            )
        if not isinstance(payload, dict):
            return SourceFetchResult(SourceResultStatus.INVALID)
        candidates: list[SourceCandidate] = []
        for signal in _serp_signals(payload)[: self.max_results]:
            evidence_url = signal.link or _public_trends_url(region=region, term=signal.term)
            observed = self.now().astimezone(UTC)
            candidates.append(
                SourceCandidate(
                    title=signal.term,
                    summary="Señal relacionada de Google Trends.",
                    region=region,
                    category=category,
                    observed_at=observed,
                    evidence=(SourceEvidence(evidence_url, observed, region, signal.confidence),),
                )
            )
        return SourceFetchResult(
            SourceResultStatus.SUCCESS if candidates else SourceResultStatus.EMPTY,
            tuple(candidates),
        )


@dataclass(frozen=True)
class SerpTrendSignal:
    term: str
    confidence: float
    link: str | None


def _public_trends_url(*, region: str, term: str) -> str:
    params = {"hl": _language(region), "q": term}
    if region != "GLOBAL":
        params["geo"] = region
    return "https://trends.google.com/trends/explore?" + urlencode(params)


def _public_trends_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "trends.google.com"
        or parsed.username
        or parsed.password
    ):
        return None
    return value


def _signal_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if value >= 0 else None
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace(",", "")
    if normalized.endswith("%"):
        normalized = normalized[:-1]
    if normalized.startswith("+"):
        normalized = normalized[1:]
    if not normalized or not re.fullmatch(r"\d+(?:\.\d+)?", normalized):
        return None
    return float(normalized)


def _signal_confidence(entry: dict[str, object]) -> float | None:
    raw = entry.get("extracted_value")
    value = _signal_number(raw)
    if value is None:
        value = _signal_number(entry.get("value"))
    if value is not None:
        if value <= 100:
            return round(0.25 + (0.60 * value / 100), 4)
        return round(min(0.95, 0.85 + ((value - 100) / 49_000)), 4)
    # The provider's documented Breakout sentinel is language-independent.
    if isinstance(entry.get("value"), str) and entry["value"].strip().casefold() == "breakout":
        return 0.95
    return None


def _serp_signals(payload: dict[str, object]) -> list[SerpTrendSignal]:
    signals: list[SerpTrendSignal] = []
    seen: set[str] = set()
    for field in ("related_queries", "related_topics"):
        groups = payload.get(field)
        if not isinstance(groups, dict):
            continue
        for group in ("rising", "top"):
            entries = groups.get(group)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                if field == "related_queries":
                    term = clean_text(entry.get("query"), limit=240)
                else:
                    topic = entry.get("topic")
                    term = clean_text(
                        topic.get("title") or topic.get("value") if isinstance(topic, dict) else None,
                        limit=240,
                    )
                confidence = _signal_confidence(entry)
                normalized = term.casefold()
                if term and confidence is not None and normalized not in seen:
                    seen.add(normalized)
                    signals.append(SerpTrendSignal(term, confidence, _public_trends_link(entry.get("link"))))
    return signals


@dataclass(frozen=True)
class RssFeed:
    identifier: str
    public_name: str
    feed_url: str
    regions: tuple[str, ...]
    categories: tuple[str, ...]


@dataclass(frozen=True)
class PinnedRssRequest:
    url: str
    host: str
    address: str
    max_response_bytes: int


@dataclass(frozen=True)
class PinnedRssResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


class RssResponseTooLarge(Exception):
    pass


class AsyncioPinnedRssConnector:
    """HTTPS connector that dials the validated address while preserving SNI."""

    async def fetch(self, request: PinnedRssRequest, *, timeout_seconds: float) -> PinnedRssResponse:
        parsed = urlsplit(request.url)
        target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        context = ssl.create_default_context()
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    request.address,
                    443,
                    ssl=context,
                    server_hostname=request.host,
                ),
                timeout=timeout_seconds,
            )
            writer.write(
                (
                    f"GET {target} HTTP/1.1\r\nHost: {request.host}\r\n"
                    "Accept: application/rss+xml, application/atom+xml, application/xml, text/xml\r\n"
                    "Accept-Encoding: identity\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
            )
            await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
            header_block = await asyncio.wait_for(
                reader.readuntil(b"\r\n\r\n"), timeout=timeout_seconds
            )
            if len(header_block) > RSS_MAX_HEADER_BYTES:
                raise ValueError("RSS headers too large")
            status_code, headers = _parse_http_headers(header_block)
            body = await _read_pinned_body(
                reader,
                headers=headers,
                maximum=request.max_response_bytes,
                timeout_seconds=timeout_seconds,
            )
            return PinnedRssResponse(status_code, headers, body)
        finally:
            if writer is not None:
                writer.close()
                with suppress(OSError):
                    await writer.wait_closed()


class HttpxPinnedTestConnector:
    """Test-only bridge: preserves the selected IP in request extensions."""

    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self.transport = transport

    async def fetch(self, request: PinnedRssRequest, *, timeout_seconds: float) -> PinnedRssResponse:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            limits=HTTP_LIMITS,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            response = await client.get(
                request.url,
                headers={"Host": request.host, "Accept-Encoding": "identity"},
                extensions={"hitrendy_pinned_ip": request.address},
            )
        body = response.content
        if len(body) > request.max_response_bytes:
            raise RssResponseTooLarge()
        return PinnedRssResponse(response.status_code, dict(response.headers), body)


def _public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _parse_http_headers(value: bytes) -> tuple[int, dict[str, str]]:
    lines = value.decode("iso-8859-1").split("\r\n")
    status = lines[0].split(" ", 2)
    if len(status) < 2 or not status[1].isdigit():
        raise ValueError("Invalid RSS response")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, separator, header_value = line.partition(":")
        if not separator:
            raise ValueError("Invalid RSS response header")
        headers[name.strip().lower()] = header_value.strip()
    return int(status[1]), headers


async def _read_pinned_body(
    reader: asyncio.StreamReader,
    *,
    headers: dict[str, str],
    maximum: int,
    timeout_seconds: float,
) -> bytes:
    deadline = asyncio.get_running_loop().time() + timeout_seconds

    async def bounded(awaitable):
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError
        return await asyncio.wait_for(awaitable, timeout=remaining)

    if headers.get("content-encoding", "identity").casefold() not in {"", "identity"}:
        raise ValueError("Compressed RSS is not accepted")
    if headers.get("transfer-encoding", "").casefold() == "chunked":
        chunks: list[bytes] = []
        size = 0
        while True:
            line = await bounded(reader.readline())
            if not line:
                raise ValueError("Incomplete RSS chunk")
            try:
                length = int(line.split(b";", 1)[0].strip(), 16)
            except ValueError as exc:
                raise ValueError("Invalid RSS chunk") from exc
            if length == 0:
                await bounded(reader.readuntil(b"\r\n"))
                break
            size += length
            if size > maximum:
                raise RssResponseTooLarge()
            chunks.append(await bounded(reader.readexactly(length)))
            if await bounded(reader.readexactly(2)) != b"\r\n":
                raise ValueError("Invalid RSS chunk")
        return b"".join(chunks)
    length_value = headers.get("content-length")
    if length_value is not None:
        try:
            length = int(length_value)
        except ValueError as exc:
            raise ValueError("Invalid RSS length") from exc
        if length < 0 or length > maximum:
            raise RssResponseTooLarge()
        return await bounded(reader.readexactly(length))
    chunks = []
    size = 0
    while True:
        chunk = await bounded(reader.read(min(65_536, maximum - size + 1)))
        if not chunk:
            break
        size += len(chunk)
        if size > maximum:
            raise RssResponseTooLarge()
        chunks.append(chunk)
    return b"".join(chunks)


def _rss_url_parts(url: str, *, allowed_hosts: set[str]) -> tuple[str, str] | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not host
        or host not in allowed_hosts
        or parsed.username
        or parsed.password
        or port not in {None, 443}
    ):
        return None
    return url, host


def validate_rss_url(
    url: str,
    *,
    allowed_hosts: set[str],
    resolver: Callable[[str], list[str]],
) -> str | None:
    parts = _rss_url_parts(url, allowed_hosts=allowed_hosts)
    if parts is None:
        return None
    _, host = parts
    try:
        addresses = resolver(host)
        if not addresses or not all(_public_ip(address) for address in addresses):
            return None
    except (OSError, ValueError):
        return None
    return url


def validate_rss_evidence_url(url: str) -> str | None:
    """Validate a stored public link without resolving or connecting to it."""

    if not isinstance(url, str) or not url.strip():
        return None
    parsed = urlsplit(url.strip())
    host = parsed.hostname
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not host
        or parsed.username
        or parsed.password
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    standard_port = 80 if parsed.scheme.casefold() == "http" else 443
    if port not in {None, standard_port}:
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii").casefold()
        except UnicodeError:
            return None
        if (
            len(ascii_host) > 253
            or any(
                not label
                or len(label) > 63
                or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
                for label in ascii_host.rstrip(".").split(".")
            )
        ):
            return None
        normalized_host = ascii_host.rstrip(".")
    else:
        if not _public_ip(str(address)):
            return None
        normalized_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
    netloc = normalized_host if port is None else f"{normalized_host}:{port}"
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            netloc,
            parsed.path or "/",
            parsed.query,
            "",
        )
    )


def _resolve(host: str) -> list[str]:
    return sorted({record[4][0] for record in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})


async def resolve_pinned_rss_url(
    url: str,
    *,
    allowed_hosts: set[str],
    resolver: Callable[[str], list[str]],
    timeout_seconds: float,
    max_response_bytes: int,
) -> PinnedRssRequest | None:
    parts = _rss_url_parts(url, allowed_hosts=allowed_hosts)
    if parts is None:
        return None
    normalized_url, host = parts
    try:
        addresses = await asyncio.wait_for(
            asyncio.to_thread(resolver, host), timeout=timeout_seconds
        )
    except (OSError, TimeoutError, ValueError):
        return None
    if not addresses or not all(isinstance(address, str) and _public_ip(address) for address in addresses):
        return None
    # Deterministic selection and no resolver call by the connection layer.
    return PinnedRssRequest(normalized_url, host, sorted(addresses)[0], max_response_bytes)


def _rss_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = _timestamp(value)
    if parsed is not None:
        return parsed
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


class RssTrendSource:
    source_type = "rss"
    available = True

    def __init__(
        self,
        *,
        feed: RssFeed,
        cache: TrendSourceCache,
        cache_ttl_seconds: int,
        negative_cache_ttl_seconds: int,
        timeout_seconds: float,
        max_results: int,
        max_response_bytes: int,
        resolver: Callable[[str], list[str]] = _resolve,
        dns_timeout_seconds: float = 3,
        connector: AsyncioPinnedRssConnector | HttpxPinnedTestConnector | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.feed, self.identifier, self.public_name = feed, f"rss-{feed.identifier}", feed.public_name
        # The declared scope of the feed: the caller skips a request outside it
        # instead of turning it into an unverified healthy result.
        self.supported_regions = feed.regions
        self.supported_categories = feed.categories
        self.cache, self.cache_ttl_seconds = cache, cache_ttl_seconds
        self.negative_cache_ttl_seconds = negative_cache_ttl_seconds
        self.timeout_seconds, self.max_results = timeout_seconds, max_results
        self.max_response_bytes, self.resolver = max_response_bytes, resolver
        self.dns_timeout_seconds = dns_timeout_seconds
        self.connector = connector or (
            HttpxPinnedTestConnector(transport) if transport is not None else AsyncioPinnedRssConnector()
        )

    async def fetch(self, *, region: str, category: str | None) -> SourceFetchResult:
        key = cache_key(
            source=self.identifier, adapter_version=ADAPTER_VERSION, region=region,
            category=category, query=self.feed.feed_url,
            public_parameters=(f"max-results={self.max_results}",),
        )
        cached = await self.cache.get(key)
        if cached is not None:
            return cached

        async def fresh() -> SourceFetchResult:
            result = await self._fetch_network(region=region, category=category)
            if result.status in {SourceResultStatus.SUCCESS, SourceResultStatus.EMPTY}:
                await self.cache.set(
                    key, result,
                    ttl_seconds=self.cache_ttl_seconds if result.status == SourceResultStatus.SUCCESS else self.negative_cache_ttl_seconds,
                )
            return result

        try:
            return await self.cache.coalesce(
                key,
                fresh,
                operation_deadline_seconds=self.timeout_seconds,
            )
        except (CacheLeaseBusy, TimeoutError):
            return SourceFetchResult(SourceResultStatus.TIMEOUT)

    async def _fetch_network(self, *, region: str, category: str | None) -> SourceFetchResult:
        allowed_hosts = {urlsplit(self.feed.feed_url).hostname or ""}
        request = await resolve_pinned_rss_url(
            self.feed.feed_url,
            allowed_hosts=allowed_hosts,
            resolver=self.resolver,
            timeout_seconds=self.dns_timeout_seconds,
            max_response_bytes=self.max_response_bytes,
        )
        if request is None:
            return SourceFetchResult(SourceResultStatus.INVALID)
        try:
            for _ in range(3):
                response = await self.connector.fetch(request, timeout_seconds=self.timeout_seconds)
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    next_url = urljoin(request.url, location) if location else None
                    request = await resolve_pinned_rss_url(
                        next_url or "",
                        allowed_hosts=allowed_hosts,
                        resolver=self.resolver,
                        timeout_seconds=self.dns_timeout_seconds,
                        max_response_bytes=self.max_response_bytes,
                    )
                    if request is None:
                        return SourceFetchResult(SourceResultStatus.INVALID)
                    continue
                if response.status_code >= 400:
                    return SourceFetchResult(SourceResultStatus.ERROR)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in {"application/rss+xml", "application/atom+xml", "application/xml", "text/xml"}:
                    return SourceFetchResult(SourceResultStatus.INVALID)
                return self._parse(response.body, region=region, category=category)
            return SourceFetchResult(SourceResultStatus.INVALID)
        except (TimeoutError, httpx.TimeoutException):
            return SourceFetchResult(SourceResultStatus.TIMEOUT)
        except (RssResponseTooLarge, ValueError):
            return SourceFetchResult(SourceResultStatus.INVALID)
        except (httpx.HTTPError, OSError):
            # The source contract only exposes a safe aggregate error.
            return SourceFetchResult(SourceResultStatus.ERROR)

    def _parse(self, raw: bytes, *, region: str, category: str | None) -> SourceFetchResult:
        try:
            root = ElementTree.fromstring(raw)
        except (DefusedXmlException, ElementTree.ParseError):
            return SourceFetchResult(SourceResultStatus.INVALID)
        entries = root.findall("./channel/item")
        atom = "{http://www.w3.org/2005/Atom}"
        if root.tag == f"{atom}feed":
            entries = root.findall(f"{atom}entry")
        candidates: list[SourceCandidate] = []
        for entry in entries[: self.max_results]:
            if root.tag == f"{atom}feed":
                title = clean_text(entry.findtext(f"{atom}title"), limit=240)
                link = next(
                    (node.get("href") for node in entry.findall(f"{atom}link") if node.get("rel", "alternate") == "alternate"),
                    None,
                )
                date = _rss_time(entry.findtext(f"{atom}published") or entry.findtext(f"{atom}updated"))
                summary = clean_text(entry.findtext(f"{atom}summary") or entry.findtext(f"{atom}content"))
            else:
                title = clean_text(entry.findtext("title"), limit=240)
                link = entry.findtext("link")
                date = _rss_time(entry.findtext("pubDate") or entry.findtext("date"))
                summary = clean_text(entry.findtext("description"))
            if not title or not isinstance(link, str) or not date:
                continue
            public_link = validate_rss_evidence_url(link)
            if public_link is None:
                continue
            candidates.append(
                SourceCandidate(
                    title=title, summary=summary, region=region, category=category, observed_at=date,
                    evidence=(SourceEvidence(public_link, date, region, 0.55),),
                )
            )
        return SourceFetchResult(
            SourceResultStatus.SUCCESS if candidates else SourceResultStatus.EMPTY,
            tuple(candidates),
        )
