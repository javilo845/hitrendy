from __future__ import annotations

import hmac
import secrets

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.cookies import CSRF_COOKIE, SESSION_COOKIE, SIGNUP_COOKIE
from app.core.csrf import (
    CSRF_CONTEXT_SESSION,
    CSRF_CONTEXT_SIGNUP,
    _generate_csrf_token,
    should_validate_csrf,
)


def test_csrf_token_generation() -> None:
    token = secrets.token_urlsafe(32)
    csrf = _generate_csrf_token(token, CSRF_CONTEXT_SESSION)
    assert isinstance(csrf, str)
    assert len(csrf) > 0


def test_csrf_token_deterministic() -> None:
    token = "test-session-token"
    first = _generate_csrf_token(token, CSRF_CONTEXT_SESSION)
    second = _generate_csrf_token(token, CSRF_CONTEXT_SESSION)
    assert first == second
    assert hmac.compare_digest(first, second)


def test_csrf_token_differs_for_different_sessions() -> None:
    t1 = _generate_csrf_token("session-a", CSRF_CONTEXT_SESSION)
    t2 = _generate_csrf_token("session-b", CSRF_CONTEXT_SESSION)
    assert t1 != t2


def test_csrf_token_differs_for_different_contexts() -> None:
    token = "same-token-value"
    session_csrf = _generate_csrf_token(token, CSRF_CONTEXT_SESSION)
    signup_csrf = _generate_csrf_token(token, CSRF_CONTEXT_SIGNUP)
    assert session_csrf != signup_csrf


def test_csrf_signup_cross_context_rejected() -> None:
    from app.core.csrf import _validate_csrf_token

    token = "some-token"
    session_csrf = _generate_csrf_token(token, CSRF_CONTEXT_SESSION)
    assert not _validate_csrf_token(token, session_csrf, CSRF_CONTEXT_SIGNUP)


def test_csrf_should_validate_mutation() -> None:
    assert should_validate_csrf("/api/v1/businesses", "POST") is True
    assert should_validate_csrf("/api/v1/auth/signup/complete", "POST") is True
    assert should_validate_csrf("/api/v1/auth/signup", "DELETE") is True
    assert should_validate_csrf("/api/v1/auth/signup", "PATCH") is True


def test_csrf_skips_safe_methods() -> None:
    assert should_validate_csrf("/api/v1/businesses", "GET") is False
    assert should_validate_csrf("/api/v1/businesses", "HEAD") is False
    assert should_validate_csrf("/api/v1/businesses", "OPTIONS") is False


def test_csrf_skips_health() -> None:
    assert should_validate_csrf("/health/live", "POST") is False
    assert should_validate_csrf("/health/ready", "POST") is False


def test_csrf_skips_google_callback() -> None:
    assert should_validate_csrf("/api/v1/auth/google/callback", "GET") is False


def test_csrf_protects_signup_endpoints() -> None:
    for path in [
        "/api/v1/auth/signup/start",
        "/api/v1/auth/signup",
        "/api/v1/auth/signup/complete",
    ]:
        assert should_validate_csrf(path, "POST") is True, f"{path} should require CSRF"
        assert should_validate_csrf(path, "DELETE") is True, f"{path} should require CSRF"


def test_csrf_protects_login() -> None:
    assert should_validate_csrf("/api/v1/auth/login", "POST") is True


def test_csrf_protects_logout() -> None:
    assert should_validate_csrf("/api/v1/auth/logout", "POST") is True


def test_csrf_skips_oauth_start() -> None:
    assert should_validate_csrf("/api/v1/auth/google/start", "GET") is False
    assert should_validate_csrf("/api/v1/auth/google/status", "GET") is False


@pytest.mark.asyncio
async def test_csrf_middleware_rejects_missing_token() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, "test-session")
            response = await client.post("/api/v1/auth/login", json={"email": "test@test.com", "password": "password"})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_middleware_rejects_invalid_token() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, "test-session")
            client.cookies.set(CSRF_COOKIE, "invalid-csrf-token")
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@test.com", "password": "password"},
                headers={"X-CSRF-Token": "invalid-csrf-token"},
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_middleware_rejects_mismatched_token() -> None:
    from app.core.csrf import CSRF_CONTEXT_SESSION, _generate_csrf_token
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        session_token = "test-session"
        valid_csrf = _generate_csrf_token(session_token, CSRF_CONTEXT_SESSION)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, session_token)
            client.cookies.set(CSRF_COOKIE, valid_csrf)
            response = await client.post(
                "/api/v1/auth/login",
                json={"email": "test@test.com", "password": "password"},
                headers={"X-CSRF-Token": "different-token"},
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_MISMATCH"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_allows_safe_methods_without_token() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, "test-session")
            response = await client.get("/api/v1/auth/google/status")
        assert response.status_code == 200
    finally:
        settings.csrf_enabled = original_enabled


# --- Signup CSRF tests ---

@pytest.mark.asyncio
async def test_csrf_signup_patch_with_valid_token() -> None:
    from app.core.cookies import SIGNUP_COOKIE
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        signup_token = "test-signup-token"
        csrf_token = _generate_csrf_token(signup_token, CSRF_CONTEXT_SIGNUP)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, signup_token)
            client.cookies.set(CSRF_COOKIE, csrf_token)
            response = await client.patch(
                "/api/v1/auth/signup",
                json={"step": "business", "business": {"name": "Test"}},
                headers={"X-CSRF-Token": csrf_token},
            )
        assert response.status_code in {200, 404, 422}
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_signup_patch_without_header() -> None:
    from app.core.cookies import SIGNUP_COOKIE
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        signup_token = "test-signup-token"
        csrf_token = _generate_csrf_token(signup_token, CSRF_CONTEXT_SIGNUP)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, signup_token)
            client.cookies.set(CSRF_COOKIE, csrf_token)
            response = await client.patch(
                "/api/v1/auth/signup",
                json={"step": "business", "business": {"name": "Test"}},
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_signup_patch_without_csrf_cookie() -> None:
    from app.core.cookies import SIGNUP_COOKIE
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        signup_token = "test-signup-token"
        csrf_token = _generate_csrf_token(signup_token, CSRF_CONTEXT_SIGNUP)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, signup_token)
            response = await client.patch(
                "/api/v1/auth/signup",
                json={"step": "business", "business": {"name": "Test"}},
                headers={"X-CSRF-Token": csrf_token},
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_MISSING"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_signup_token_from_another_account() -> None:
    from app.core.cookies import SIGNUP_COOKIE
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        signup_token = "signup-token-a"
        other_signup_token = "signup-token-b"
        csrf_token = _generate_csrf_token(other_signup_token, CSRF_CONTEXT_SIGNUP)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, signup_token)
            client.cookies.set(CSRF_COOKIE, csrf_token)
            response = await client.patch(
                "/api/v1/auth/signup",
                json={"step": "business", "business": {"name": "Test"}},
                headers={"X-CSRF-Token": csrf_token},
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_session_token_is_selected_when_both_cookies_are_present() -> None:
    from app.core.cookies import SIGNUP_COOKIE
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        signup_token = "signup-token"
        session_token = "session-token"
        session_csrf = _generate_csrf_token(session_token, CSRF_CONTEXT_SESSION)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, session_token)
            client.cookies.set(SIGNUP_COOKIE, signup_token)
            client.cookies.set(CSRF_COOKIE, session_csrf)
            response = await client.patch(
                "/api/v1/auth/signup",
                json={"step": "business", "business": {"name": "Test"}},
                headers={"X-CSRF-Token": session_csrf},
            )
        assert response.status_code == 422
        assert response.json()["detail"]
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_signup_token_used_with_session_endpoint() -> None:
    from app.core.cookies import SIGNUP_COOKIE
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        signup_token = "signup-token"
        signup_csrf = _generate_csrf_token(signup_token, CSRF_CONTEXT_SIGNUP)
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, "session-token")
            client.cookies.set(SIGNUP_COOKIE, signup_token)
            client.cookies.set(CSRF_COOKIE, signup_csrf)
            response = await client.post(
                "/api/v1/auth/logout",
                headers={"X-CSRF-Token": signup_csrf},
            )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_signup_patch_protected() -> None:
    assert should_validate_csrf("/api/v1/auth/signup", "PATCH") is True


@pytest.mark.asyncio
async def test_csrf_signup_delete_protected() -> None:
    assert should_validate_csrf("/api/v1/auth/signup", "DELETE") is True


@pytest.mark.asyncio
async def test_csrf_signup_complete_protected() -> None:
    assert should_validate_csrf("/api/v1/auth/signup/complete", "POST") is True


@pytest.mark.asyncio
async def test_csrf_signup_get_allowed_without_token() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set("hitrendy_signup", "some-token")
            response = await client.get("/api/v1/auth/google/status")
        assert response.status_code == 200
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_oauth_callback_allowed() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/google/callback?code=test&state=test")
        assert response.status_code in {302, 303, 400, 403, 500}
    finally:
        settings.csrf_enabled = original_enabled


def test_csrf_endpoint_exempt() -> None:
    assert should_validate_csrf("/api/v1/auth/csrf", "GET") is False


@pytest.mark.asyncio
async def test_csrf_endpoint_with_session() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, "test-session")
            response = await client.get("/api/v1/auth/csrf")
        assert response.status_code == 200
        body = response.json()
        assert body["token"] is not None
        assert isinstance(body["token"], str)
        assert len(body["token"]) > 0
        assert response.headers.get("cache-control") == "no-store"
        assert CSRF_COOKIE in response.headers.get("set-cookie", "")
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_endpoint_with_signup() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, "test-signup")
            response = await client.get("/api/v1/auth/csrf")
        assert response.status_code == 200
        body = response.json()
        assert body["token"] is not None
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_endpoint_without_context() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/csrf")
        assert response.status_code == 200
        body = response.json()
        assert body["token"] is None
        assert response.headers.get("cache-control") == "no-store"
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_endpoint_context_promotion() -> None:
    from app.core.csrf import _validate_csrf_token
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, "signup-token")
            response = await client.get("/api/v1/auth/csrf")
            signup_body = response.json()
            client.cookies.set(SESSION_COOKIE, "session-token")
            response = await client.get("/api/v1/auth/csrf")
            session_body = response.json()
        assert signup_body["token"] is not None
        assert session_body["token"] is not None
        assert signup_body["token"] != session_body["token"]
        assert not _validate_csrf_token("session-token", signup_body["token"], CSRF_CONTEXT_SESSION)
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_endpoint_token_rotation_on_promotion() -> None:
    from app.core.csrf import CSRF_CONTEXT_SESSION, _generate_csrf_token
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SIGNUP_COOKIE, "signup-token")
            response = await client.get("/api/v1/auth/csrf")
            response.json()
            client.cookies.set(SESSION_COOKIE, "session-token")
            response = await client.get("/api/v1/auth/csrf")
            session_body = response.json()
        session_expected = _generate_csrf_token("session-token", CSRF_CONTEXT_SESSION)
        assert session_body["token"] == session_expected
    finally:
        settings.csrf_enabled = original_enabled


@pytest.mark.asyncio
async def test_csrf_endpoint_allows_cors_allowed_origin() -> None:
    from app.main import app as main_app

    main_app.dependency_overrides.clear()
    original_enabled = settings.csrf_enabled
    try:
        settings.csrf_enabled = True
        async with AsyncClient(transport=ASGITransport(app=main_app), base_url="http://test") as client:
            client.cookies.set(SESSION_COOKIE, "session")
            response = await client.get(
                "/api/v1/auth/csrf",
                headers={"Origin": "http://localhost:3000"},
            )
        assert response.status_code == 200
    finally:
        settings.csrf_enabled = original_enabled
