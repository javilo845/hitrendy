from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.business.models import Business
from app.core.config import settings
from app.core.cookies import SIGNUP_COOKIE as SIGNUP_COOKIE_NAME
from app.core.errors import AppError
from app.dependencies import get_db
from app.identity.models import PendingSignup, User, UserPreference

BUSINESS_DRAFT = {
    "name": "Café de registro",
    "category": "gastronomy",
    "country": "Honduras",
    "city": "Tegucigalpa",
    "description": "Café de especialidad.",
    "primary_product": "Café artesanal",
    "target_audience": "Personas que trabajan cerca",
    "website_url": "https://example.com",
}
CHANNELS_DRAFT = {
    "preferred_platforms": ["instagram", "tiktok"],
    "primary_objective": "sales",
}
BRAND_DRAFT = {
    "voice_tones": ["friendly"],
    "value_proposition": "Café artesanal para tu día.",
    "preferred_words": ["artesanal"],
    "forbidden_words": ["barato"],
    "primary_color": "#541787",
    "content_locale": "es",
}


async def _start_signup(client: AsyncClient, email: str) -> tuple[int, str]:
    client.cookies.delete(settings.session_cookie_name)
    response = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": email,
            "name": "Ana Registro",
            "password": "una-clave-segura-123",
            "interface_locale": "es",
        },
    )
    assert response.status_code == 201, response.text
    token = response.cookies.get(SIGNUP_COOKIE_NAME)
    assert token
    return response.json()["signup"]["version"], token


@pytest.mark.asyncio
async def test_authenticated_session_cannot_start_pending_signup(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": "pending@example.com",
            "name": "Cuenta activa",
            "password": "una-clave-segura-123",
            "interface_locale": "es",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_AUTHENTICATED"


async def _complete_draft(client: AsyncClient, email: str) -> str:
    version, token = await _start_signup(client, email)
    for step, payload in (
        ("business", BUSINESS_DRAFT),
        ("channels", CHANNELS_DRAFT),
        ("brand", BRAND_DRAFT),
        ("review", {"confirmed": True}),
    ):
        response = await client.patch(
            "/api/v1/auth/signup",
            json={"step": step, "expected_version": version, step: payload},
        )
        assert response.status_code == 200, response.text
        version = response.json()["signup"]["version"]
    return token


@pytest.mark.asyncio
async def test_private_routes_fail_closed_without_session() -> None:
    from httpx import ASGITransport

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/v1/businesses")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_session_cannot_select_unowned_workspace(client: AsyncClient) -> None:
    response = await client.get("/api/v1/businesses", headers={"X-Workspace-Id": "ws_not_a_member"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_logout_invalidates_the_session(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    response = await client.get("/api/v1/businesses")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_rotates_existing_sessions_and_sets_a_strict_cookie(
    client: AsyncClient,
) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "rotation@example.com",
            "name": "Rotation Test",
            "password": "una-clave-segura-123",
            "workspace_name": "Rotation workspace",
        },
    )
    assert register.status_code == 201
    stale_token = register.cookies.get(settings.session_cookie_name)
    assert stale_token
    set_cookie = register.headers["set-cookie"].casefold()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "rotation@example.com", "password": "una-clave-segura-123"},
    )
    assert login.status_code == 200
    assert login.cookies.get(settings.session_cookie_name) != stale_token

    from httpx import ASGITransport

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stale:
        stale.cookies.set(settings.session_cookie_name, stale_token)
        response = await stale.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_signup_start_persists_only_a_pending_hash(client: AsyncClient) -> None:
    email = "pending-only@example.com"
    _, _ = await _start_signup(client, email)
    progress = await client.get("/api/v1/auth/signup")
    assert progress.status_code == 200
    assert progress.json()["signup"]["status"] == "pending"
    assert progress.json()["signup"]["current_step"] == "business"
    assert "password" not in str(progress.json()).casefold()

    async for session in app_dependent_sessions():
        pending = (await session.execute(select(PendingSignup).where(PendingSignup.email_normalized == email))).scalar_one()
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        assert pending.password_hash.startswith("scrypt$")
        assert pending.password_hash != "una-clave-segura-123"
        assert user is None


async def app_dependent_sessions():
    async for session in app_get_db_override():
        yield session


def app_get_db_override():
    from app.main import app

    return app.dependency_overrides[get_db]()


@pytest.mark.asyncio
async def test_signup_draft_is_versioned_and_idempotent(client: AsyncClient) -> None:
    version, _ = await _start_signup(client, "versioned-draft@example.com")
    first = await client.patch(
        "/api/v1/auth/signup",
        json={"step": "business", "expected_version": version, "business": BUSINESS_DRAFT},
    )
    assert first.status_code == 200
    next_version = first.json()["signup"]["version"]

    repeat = await client.patch(
        "/api/v1/auth/signup",
        json={"step": "business", "expected_version": version, "business": BUSINESS_DRAFT},
    )
    assert repeat.status_code == 200
    assert repeat.json()["signup"]["version"] == next_version

    conflict = await client.patch(
        "/api/v1/auth/signup",
        json={
            "step": "business",
            "expected_version": version,
            "business": {**BUSINESS_DRAFT, "name": "Otro negocio"},
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "SIGNUP_CONFLICT"


@pytest.mark.asyncio
async def test_signup_complete_creates_active_account_atomically(client: AsyncClient) -> None:
    email = "complete-signup@example.com"
    await _complete_draft(client, email)
    complete = await client.post(
        "/api/v1/auth/signup/complete",
        headers={"Idempotency-Key": "signup-complete-001"},
    )
    assert complete.status_code == 200, complete.text
    payload = complete.json()
    assert payload["user"]["email"] == email
    assert payload["business"]["workspace_id"] == payload["workspace"]["id"]
    assert payload["business"]["content_locale"] == "es"
    assert payload["brand_profile"]["business_id"] == payload["business"]["id"]
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    async for session in app_dependent_sessions():
        user = (await session.execute(select(User).where(User.email == email))).scalar_one()
        preference = await session.get(UserPreference, user.id)
        pending = (
            await session.execute(select(PendingSignup).where(PendingSignup.email_normalized == email))
        ).scalar_one()
        assert user.status == "active"
        assert preference is not None
        assert pending.completed_at is not None
        businesses = (
            await session.execute(
                select(Business).where(Business.workspace_id == payload["workspace"]["id"])
            )
        ).scalars().all()
        assert len(businesses) == 1


@pytest.mark.asyncio
async def test_signup_complete_replays_the_same_idempotency_key(client: AsyncClient) -> None:
    token = await _complete_draft(client, "idempotent-signup@example.com")
    headers = {"Idempotency-Key": "signup-complete-idempotent"}
    first = await client.post("/api/v1/auth/signup/complete", headers=headers)
    assert first.status_code == 200
    client.cookies.set(SIGNUP_COOKIE_NAME, token)
    repeated = await client.post("/api/v1/auth/signup/complete", headers=headers)
    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    client.cookies.set(SIGNUP_COOKIE_NAME, token)
    conflict = await client.post(
        "/api/v1/auth/signup/complete",
        headers={"Idempotency-Key": "signup-complete-other"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "SIGNUP_CONFLICT"


@pytest.mark.asyncio
async def test_signup_rejects_expired_or_foreign_tokens(client: AsyncClient) -> None:
    email = "expired-signup@example.com"
    _, _ = await _start_signup(client, email)
    async for session in app_dependent_sessions():
        pending = (
            await session.execute(select(PendingSignup).where(PendingSignup.email_normalized == email))
        ).scalar_one()
        pending.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    expired = await client.get("/api/v1/auth/signup")
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "SIGNUP_EXPIRED"

    client.cookies.set(SIGNUP_COOKIE_NAME, "not-a-valid-signup-token")
    foreign = await client.get("/api/v1/auth/signup")
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "SIGNUP_NOT_FOUND"


@pytest.mark.asyncio
async def test_signup_cancel_removes_the_pending_draft(client: AsyncClient) -> None:
    await _start_signup(client, "cancel-signup@example.com")
    cancelled = await client.delete("/api/v1/auth/signup")
    assert cancelled.status_code == 204
    missing = await client.get("/api/v1/auth/signup")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "SIGNUP_NOT_FOUND"


@pytest.mark.asyncio
async def test_signup_rejects_active_and_pending_email_reuse(client: AsyncClient) -> None:
    await _start_signup(client, "reserved-signup@example.com")
    pending = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": "reserved-signup@example.com",
            "name": "Otra Ana",
            "password": "otra-clave-segura-123",
            "interface_locale": "es",
        },
    )
    assert pending.status_code == 409
    assert pending.json()["error"]["code"] == "EMAIL_IN_USE"

    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "active-signup@example.com",
            "name": "Cuenta activa",
            "password": "una-clave-segura-123",
            "workspace_name": "Cuenta activa",
        },
    )
    assert registered.status_code == 201
    active = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": "active-signup@example.com",
            "name": "Cuenta activa",
            "password": "una-clave-segura-123",
            "interface_locale": "es",
        },
    )
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "ALREADY_AUTHENTICATED"


@pytest.mark.asyncio
async def test_signup_complete_rolls_back_when_business_creation_fails(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = "rollback-signup@example.com"
    await _complete_draft(client, email)

    async def fail_business(*args, **kwargs):
        del args, kwargs
        raise AppError("BUSINESS_CREATION_FAILED", "No se pudo crear el negocio.", status_code=500)

    monkeypatch.setattr("app.identity.routes.create_business", fail_business)
    response = await client.post(
        "/api/v1/auth/signup/complete",
        headers={"Idempotency-Key": "signup-rollback"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "BUSINESS_CREATION_FAILED"

    async for session in app_dependent_sessions():
        user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
        assert user is None
