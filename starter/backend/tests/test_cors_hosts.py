from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _assert_error_headers(response) -> None:
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
    assert response.headers.get("x-request-id")


@pytest.mark.asyncio
async def test_cors_allowed_origin() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code in {200, 204}
    cors_origin = response.headers.get("access-control-allow-origin")
    assert cors_origin == "http://localhost:3000"
    assert "access-control-allow-credentials" in response.headers


@pytest.mark.asyncio
async def test_cors_rejected_origin() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/health/live",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code in {200, 400}
    cors_origin = response.headers.get("access-control-allow-origin")
    assert cors_origin is None or cors_origin == "null"


@pytest.mark.asyncio
async def test_cors_valid_preflight() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-methods")
    allowed_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "content-type" in allowed_headers


@pytest.mark.asyncio
async def test_cors_preflight_rejected() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://unknown.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.status_code in {200, 400}
    cors_origin = response.headers.get("access-control-allow-origin")
    assert cors_origin is None or cors_origin == "null"


@pytest.mark.asyncio
async def test_cors_multiple_origins() -> None:
    import app.core.config as config_module

    original = config_module.settings.app_env
    try:
        config_module.settings.app_env = "test"
        from fastapi import FastAPI
        from starlette.middleware.cors import CORSMiddleware

        test_app = FastAPI()
        test_app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://localhost:4000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @test_app.get("/health/live")
        async def _hl():
            return {"status": "ok"}

        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
            response = await client.options(
                "/health/live",
                headers={
                    "Origin": "http://localhost:4000",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert response.status_code in {200, 204}
        cors_origin = response.headers.get("access-control-allow-origin")
        assert cors_origin == "http://localhost:4000"
    finally:
        config_module.settings.app_env = original


@pytest.mark.asyncio
async def test_cors_no_origin() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cors_credentials_sent() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.options(
            "/health/live",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_allowed_origin_receives_cors_and_security_headers_on_csrf_error(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "csrf_enabled", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/v1/auth/signup",
            json={"step": "business", "business": {"name": "Test"}},
            headers={
                "Origin": "http://localhost:3000",
                "Cookie": "hitrendy_signup=signup-token",
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    _assert_error_headers(response)


@pytest.mark.asyncio
async def test_allowed_origin_receives_cors_and_security_headers_on_too_large_body(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_request_body_bytes", 4)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            content=b"oversized",
            headers={"Origin": "http://localhost:3000", "Content-Length": "9"},
        )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_TOO_LARGE"
    _assert_error_headers(response)


@pytest.mark.asyncio
async def test_body_limit_counts_chunked_bytes_even_when_content_length_is_smaller(monkeypatch) -> None:
    from app.core.config import settings
    from app.main import RequestBodyLimitMiddleware

    monkeypatch.setattr(settings, "max_request_body_bytes", 4)
    received = [
        {"type": "http.request", "body": b"ab", "more_body": True},
        {"type": "http.request", "body": b"cde", "more_body": False},
    ]
    sent = []

    async def receive():
        return received.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    middleware = RequestBodyLimitMiddleware(downstream)
    await middleware(
        {"type": "http", "headers": [(b"content-length", b"4")]},
        receive,
        send,
    )
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_body_limit_allows_exact_limit(monkeypatch) -> None:
    from app.core.config import settings
    from app.main import RequestBodyLimitMiddleware

    monkeypatch.setattr(settings, "max_request_body_bytes", 4)
    received = [{"type": "http.request", "body": b"abcd", "more_body": False}]
    sent = []

    async def receive():
        return received.pop(0)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        await receive()
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    await RequestBodyLimitMiddleware(downstream)(
        {"type": "http", "headers": []}, receive, send
    )
    assert sent[0]["status"] == 204


async def _stream_through_application(chunks: list[bytes], headers: list[tuple[bytes, bytes]]) -> tuple[int, dict[str, str], dict]:
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [(b"host", b"test"), (b"origin", b"http://localhost:3000"), *headers],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
            "root_path": "",
        },
        receive,
        send,
    )
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = {key.decode(): value.decode() for key, value in start["headers"]}
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], response_headers, json.loads(body or b"{}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "headers"),
    [
        ([b"abc", b"def"], []),
        ([b"abc", b"def"], [(b"content-length", b"4")]),
    ],
)
async def test_full_application_rejects_streams_larger_than_limit(monkeypatch, chunks, headers) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_request_body_bytes", 4)
    status, response_headers, body = await _stream_through_application(chunks, headers)
    assert status == 413
    assert body["error"]["code"] == "REQUEST_TOO_LARGE"
    assert response_headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response_headers["x-content-type-options"] == "nosniff"
    assert response_headers["x-request-id"]


@pytest.mark.asyncio
async def test_full_application_allows_stream_exactly_at_limit(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_request_body_bytes", 4)
    status, _, body = await _stream_through_application([b"abcd"], [])
    assert status != 413
    assert body["detail"]


@pytest.mark.asyncio
async def test_allowed_host_accepted() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/live", headers={"Host": "localhost"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_forwarded_proto_not_trusted_without_proxy() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/health/live",
            headers={
                "X-Forwarded-Proto": "https",
                "X-Forwarded-For": "1.2.3.4",
            },
        )
    assert response.status_code == 200


# --- Trusted host tests ---

@pytest.mark.asyncio
async def test_host_direct_tamper_x_forwarded_host() -> None:
    import app.core.config as config_module

    original_hosts = config_module.settings.allowed_hosts_str
    config_module.settings.allowed_hosts_str = "api.example.com"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/google/status",
                headers={
                    "Host": "api.example.com",
                    "X-Forwarded-Host": "evil.com",
                },
            )
        assert response.status_code == 200
    finally:
        config_module.settings.allowed_hosts_str = original_hosts


@pytest.mark.asyncio
async def test_host_direct_x_forwarded_for_ignored() -> None:
    import app.core.config as config_module

    original_hosts = config_module.settings.allowed_hosts_str
    config_module.settings.allowed_hosts_str = "api.example.com"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/google/status",
                headers={
                    "Host": "api.example.com",
                    "X-Forwarded-For": "1.2.3.4, 10.0.0.1",
                },
            )
        assert response.status_code == 200
    finally:
        config_module.settings.allowed_hosts_str = original_hosts


@pytest.mark.asyncio
async def test_host_rejected() -> None:
    import app.core.config as config_module

    original_hosts = config_module.settings.allowed_hosts_str
    config_module.settings.allowed_hosts_str = "api.example.com"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/google/status",
                headers={"Host": "evil.com"},
            )
        assert response.status_code == 400
    finally:
        config_module.settings.allowed_hosts_str = original_hosts


@pytest.mark.asyncio
async def test_host_invalid_not_reflected_in_body() -> None:
    import app.core.config as config_module

    original_hosts = config_module.settings.allowed_hosts_str
    config_module.settings.allowed_hosts_str = "api.example.com"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/google/status",
                headers={"Host": "evil.com"},
            )
        body = response.text.lower()
        assert "evil" not in body
    finally:
        config_module.settings.allowed_hosts_str = original_hosts


@pytest.mark.asyncio
async def test_invalid_forwarded_proto_is_ignored_by_the_application() -> None:
    import app.core.config as config_module

    original_hosts = config_module.settings.allowed_hosts_str
    original_forwarded = config_module.settings.forwarded_allow_ips_str
    config_module.settings.allowed_hosts_str = "api.example.com"
    config_module.settings.forwarded_allow_ips_str = "127.0.0.1"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/auth/google/status",
                headers={
                    "Host": "api.example.com",
                    "X-Forwarded-Proto": "ftp",
                    "X-Forwarded-For": "127.0.0.1",
                },
            )
        assert response.status_code == 200
    finally:
        config_module.settings.allowed_hosts_str = original_hosts
        config_module.settings.forwarded_allow_ips_str = original_forwarded
