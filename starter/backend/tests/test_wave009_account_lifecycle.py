"""WAVE-009: deletion request, public status, access blocking and honest usage."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.models import AIUsageEvent
from app.core.config import settings
from app.core.cookies import OAUTH_COOKIE, SIGNUP_COOKIE
from app.core.errors import ForbiddenError
from app.dependencies import get_db
from app.identity.account_deletion import (
    CONFIRMATION_PHRASES,
    STATUS_TOKEN_TTL,
    read_public_deletion_status,
    request_account_deletion,
    status_token_hash,
)
from app.identity.google_oauth import GoogleIdentity
from app.identity.models import (
    AccountPurgeJob,
    AuthSession,
    OAuthAccount,
    User,
    UserPreference,
    Workspace,
    WorkspaceMember,
)
from app.main import app

PASSWORD = "una-clave-segura-123"
STATUS_PATH = "/api/v1/auth/account/deletion-status"
ALLOWED_ORIGIN = "http://localhost:3000"


def new_status_token() -> str:
    """What the browser generates before sending the request: 256 opaque bits."""

    return secrets.token_urlsafe(32)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    generator = app.dependency_overrides[get_db]()
    session = await generator.__anext__()
    try:
        yield session
    finally:
        await generator.aclose()


@asynccontextmanager
async def anonymous_client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def _register(client: AsyncClient, email: str, *, name: str = "Cuenta") -> dict:
    client.cookies.delete(settings.session_cookie_name)
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "name": name,
            "password": PASSWORD,
            "workspace_name": f"Workspace {name}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _set_locale(client: AsyncClient, locale: str, *, name: str = "Cuenta") -> dict:
    response = await client.patch(
        "/api/v1/auth/account", json={"name": name, "interface_locale": locale}
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


async def _job_for(user_id: str) -> AccountPurgeJob | None:
    async with session_scope() as session:
        return await session.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.user_id == user_id)
        )


# --------------------------------------------------------------------------- #
# Multilingual confirmation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("locale", "phrase"), sorted(CONFIRMATION_PHRASES.items()))
@pytest.mark.asyncio
async def test_confirmation_uses_the_phrase_of_the_persisted_locale(
    client: AsyncClient, locale: str, phrase: str
) -> None:
    account = await _register(client, f"confirm-{locale}@example.com")
    user = await _set_locale(client, locale)
    assert user["interface_locale"] == locale
    assert user["deletion_confirmation_phrase"] == phrase
    # /me offers exactly the phrase the server will accept.
    assert (await client.get("/api/v1/auth/me")).json()["user"][
        "deletion_confirmation_phrase"
    ] == phrase

    for wrong in ("BORRAR TODO", "delete my account", *(set(CONFIRMATION_PHRASES.values()) - {phrase})):
        rejected = await client.post(
            "/api/v1/auth/account/delete",
            json={"confirmation": wrong, "status_token": new_status_token()},
        )
        assert rejected.status_code == 422, wrong
        assert rejected.json()["error"]["code"] == "DELETE_CONFIRMATION_REQUIRED"
        assert phrase in rejected.json()["error"]["message"]

    accepted = await client.post(
        "/api/v1/auth/account/delete",
        json={"confirmation": phrase.casefold(), "status_token": new_status_token()},
    )
    assert accepted.status_code == 202, accepted.text
    assert accepted.json() == {"status": "pending"}
    assert accepted.headers["cache-control"] == "no-store"
    job = await _job_for(account["user"]["id"])
    assert job is not None and job.status == "pending"


@pytest.mark.asyncio
async def test_the_locale_survives_a_reload_and_drives_the_phrase(client: AsyncClient) -> None:
    account = await _register(client, "locale-persist@example.com")
    await _set_locale(client, "pt", name="Conta")

    async with session_scope() as session:
        preference = await session.get(UserPreference, account["user"]["id"])
        stored = await session.get(User, account["user"]["id"])
        assert preference is not None and preference.interface_locale == "pt"
        assert stored is not None and stored.interface_locale == "pt"

    reloaded = (await client.get("/api/v1/auth/me")).json()["user"]
    assert reloaded["interface_locale"] == "pt"
    assert reloaded["deletion_confirmation_phrase"] == "EXCLUIR"
    assert reloaded["name"] == "Conta"


# --------------------------------------------------------------------------- #
# Idempotency of the request
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_repeating_the_request_with_the_same_token_keeps_one_job(
    client: AsyncClient,
) -> None:
    account = await _register(client, "idempotent-delete@example.com")
    user_id = account["user"]["id"]
    token = new_status_token()

    async with session_scope() as session:
        first = await request_account_deletion(
            session, user_id=user_id, confirmation="ELIMINAR", status_token=token
        )
        first_id = first.id
    async with session_scope() as session:
        # A double click, a network retry or a replayed 202: same token, same job.
        second = await request_account_deletion(
            session, user_id=user_id, confirmation="eliminar", status_token=token
        )
        assert second.id == first_id

    async with session_scope() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccountPurgeJob)
                .where(AccountPurgeJob.user_id == user_id)
            )
            == 1
        )
        user = await session.get(User, user_id)
        assert user is not None and user.status == "deletion_pending"
        assert user.deletion_requested_at is not None
        # The first request already revoked every device.
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == user_id)
            )
            == 0
        )

    async with session_scope() as session:
        assert await read_public_deletion_status(session, token) == "pending"


@pytest.mark.asyncio
async def test_a_lost_response_can_be_retried_with_a_fresh_token(client: AsyncClient) -> None:
    account = await _register(client, "lost-response@example.com")
    user_id = account["user"]["id"]
    lost_token = new_status_token()
    retry_token = new_status_token()

    async with session_scope() as session:
        first = await request_account_deletion(
            session, user_id=user_id, confirmation="ELIMINAR", status_token=lost_token
        )
        first_id = first.id
    async with session_scope() as session:
        again = await request_account_deletion(
            session, user_id=user_id, confirmation="ELIMINAR", status_token=retry_token
        )
        assert again.id == first_id

    async with session_scope() as session:
        # The job is rebound to the token the browser actually kept.
        assert await read_public_deletion_status(session, retry_token) == "pending"
        with pytest.raises(ForbiddenError):
            await read_public_deletion_status(session, lost_token)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccountPurgeJob)
                .where(AccountPurgeJob.user_id == user_id)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_a_second_http_request_never_leaks_a_database_error(client: AsyncClient) -> None:
    await _register(client, "double-click@example.com")
    token = new_status_token()
    payload = {"confirmation": "ELIMINAR", "status_token": token}

    first = await client.post("/api/v1/auth/account/delete", json=payload)
    assert first.status_code == 202
    # The session died with the first call; the retry is refused as unauthenticated,
    # never with an integrity error, and the kept token still answers.
    repeated = await client.post("/api/v1/auth/account/delete", json=payload)
    assert repeated.status_code == 401
    assert repeated.json()["error"]["code"] == "UNAUTHENTICATED"

    async with anonymous_client() as anonymous:
        status = await anonymous.get(STATUS_PATH, headers={"X-Deletion-Status-Token": token})
    assert status.status_code == 200
    assert status.json() == {"status": "pending"}


# --------------------------------------------------------------------------- #
# Public status screen
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_the_public_status_needs_no_session_and_exposes_only_the_status(
    client: AsyncClient,
) -> None:
    account = await _register(client, "public-status@example.com")
    token = new_status_token()
    assert (
        await client.post(
            "/api/v1/auth/account/delete",
            json={"confirmation": "ELIMINAR", "status_token": token},
        )
    ).status_code == 202

    async with session_scope() as session:
        job = await session.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.user_id == account["user"]["id"])
        )
        assert job is not None
        job.last_error = "detalle interno que nadie debe ver"
        await session.commit()
        job_id, workspace_id = job.id, job.workspace_id

    async with anonymous_client() as anonymous:
        response = await anonymous.get(STATUS_PATH, headers={"X-Deletion-Status-Token": token})
        # The screen has no session and reaches nothing else.
        assert (await anonymous.get("/api/v1/auth/me")).status_code == 401
        assert (await anonymous.get("/api/v1/businesses")).status_code == 401

    assert response.status_code == 200
    assert response.json() == {"status": "pending"}
    assert response.headers["cache-control"] == "no-store"
    body = response.text
    for secret in (job_id, workspace_id, account["user"]["id"], token, "detalle interno"):
        assert secret not in body


@pytest.mark.asyncio
async def test_missing_invalid_and_expired_status_tokens_are_refused(
    client: AsyncClient,
) -> None:
    account = await _register(client, "expired-status@example.com")
    token = new_status_token()
    assert (
        await client.post(
            "/api/v1/auth/account/delete",
            json={"confirmation": "ELIMINAR", "status_token": token},
        )
    ).status_code == 202

    async with anonymous_client() as anonymous:
        missing = await anonymous.get(STATUS_PATH)
        invalid = await anonymous.get(
            STATUS_PATH, headers={"X-Deletion-Status-Token": new_status_token()}
        )
    for response in (missing, invalid):
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "El token de estado no es válido."
        assert response.headers["cache-control"] == "no-store"

    async with session_scope() as session:
        job = await session.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.user_id == account["user"]["id"])
        )
        assert job is not None
        assert job.status_token_hash == status_token_hash(token)
        job.status_token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with anonymous_client() as anonymous:
        expired = await anonymous.get(STATUS_PATH, headers={"X-Deletion-Status-Token": token})
    assert expired.status_code == 403
    assert expired.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_the_status_token_is_stored_only_as_a_hash(client: AsyncClient) -> None:
    account = await _register(client, "hashed-token@example.com")
    token = new_status_token()
    assert (
        await client.post(
            "/api/v1/auth/account/delete",
            json={"confirmation": "ELIMINAR", "status_token": token},
        )
    ).status_code == 202

    async with session_scope() as session:
        job = await session.scalar(
            select(AccountPurgeJob).where(AccountPurgeJob.user_id == account["user"]["id"])
        )
        assert job is not None
        assert job.status_token_hash == status_token_hash(token)
        assert token not in str(job.__dict__)
        expires_at = job.status_token_expires_at
        assert expires_at is not None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        assert expires_at <= datetime.now(UTC) + STATUS_TOKEN_TTL + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_a_weak_status_token_is_rejected_by_the_contract(client: AsyncClient) -> None:
    await _register(client, "weak-token@example.com")
    for weak in ("corto", "a" * 42, "con espacios y símbolos!" * 2):
        response = await client.post(
            "/api/v1/auth/account/delete",
            json={"confirmation": "ELIMINAR", "status_token": weak},
        )
        assert response.status_code == 422, weak
    assert await _job_for("usr_test_001") is None


# --------------------------------------------------------------------------- #
# CORS
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_preflight_allows_the_deletion_status_header_for_an_allowed_origin() -> None:
    async with anonymous_client() as anonymous:
        response = await anonymous.options(
            STATUS_PATH,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-deletion-status-token",
            },
        )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    allowed = response.headers.get("access-control-allow-headers", "").casefold()
    assert "x-deletion-status-token" in allowed


@pytest.mark.asyncio
async def test_preflight_from_an_unknown_origin_is_still_blocked() -> None:
    async with anonymous_client() as anonymous:
        response = await anonymous.options(
            STATUS_PATH,
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-deletion-status-token",
            },
        )
    origin = response.headers.get("access-control-allow-origin")
    assert origin is None or origin == "null"


# --------------------------------------------------------------------------- #
# Access blocking
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_deletion_pending_blocks_every_way_back_in(client: AsyncClient) -> None:
    email = "blocked@example.com"
    account = await _register(client, email, name="Bloqueada")
    user_id = account["user"]["id"]
    session_cookie = client.cookies.get(settings.session_cookie_name)

    # A second device, logged in before the request.
    async with anonymous_client() as other_device:
        login = await other_device.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert login.status_code == 200
        other_cookie = other_device.cookies.get(settings.session_cookie_name)

    victim = await _register(client, "intact-b@example.com", name="Usuaria B")
    victim_cookie = client.cookies.get(settings.session_cookie_name)

    async with session_scope() as session:
        await request_account_deletion(
            session, user_id=user_id, confirmation="ELIMINAR", status_token=new_status_token()
        )

    async with anonymous_client() as anonymous:
        for cookie in (session_cookie, other_cookie):
            anonymous.cookies.set(settings.session_cookie_name, cookie)
            assert (await anonymous.get("/api/v1/auth/me")).status_code == 401
            assert (await anonymous.get("/api/v1/businesses")).status_code == 401
            anonymous.cookies.clear()

        password_login = await anonymous.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert password_login.status_code == 403
        assert password_login.cookies.get(settings.session_cookie_name) is None

        # A new signup cannot resurrect the address either.
        signup = await anonymous.post(
            "/api/v1/auth/signup/start",
            json={
                "email": email,
                "name": "Bloqueada otra vez",
                "password": PASSWORD,
                "interface_locale": "es",
            },
        )
        assert signup.status_code == 409
        assert signup.json()["error"]["code"] == "EMAIL_IN_USE"
        assert signup.cookies.get(SIGNUP_COOKIE) is None

        # User B keeps working.
        anonymous.cookies.set(settings.session_cookie_name, victim_cookie)
        assert (await anonymous.get("/api/v1/auth/me")).json()["user"]["id"] == victim["user"]["id"]

    async with session_scope() as session:
        intact = await session.get(User, victim["user"]["id"])
        assert intact is not None and intact.status == "active"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(WorkspaceMember)
                .where(WorkspaceMember.user_id == victim["user"]["id"])
            )
            == 1
        )


@pytest.mark.asyncio
async def test_google_sign_in_is_refused_for_an_account_pending_deletion(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "google_sign_in_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", "google-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "google-client-secret")
    monkeypatch.setattr(
        settings, "google_redirect_uri", "http://test/api/v1/auth/google/callback"
    )
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")
    monkeypatch.setattr(settings, "google_oauth_state_ttl_seconds", 600)

    account = await _register(client, "oauth-blocked@example.com", name="OAuth")
    user_id = account["user"]["id"]
    async with session_scope() as session:
        session.add(
            OAuthAccount(
                user_id=user_id,
                provider="google",
                provider_subject="google-blocked",
                email_at_link_time="oauth-blocked@example.com",
            )
        )
        await session.commit()
        await request_account_deletion(
            session, user_id=user_id, confirmation="ELIMINAR", status_token=new_status_token()
        )

    identity = GoogleIdentity("google-blocked", "oauth-blocked@example.com", "OAuth")

    class FakeGoogle:
        def authorization_url(self, **kwargs: str) -> str:
            return f"https://accounts.google.com/mock?{urlencode(kwargs)}"

        async def exchange_code(self, *, code: str, code_verifier: str) -> str:
            del code, code_verifier
            return "fake-id-token"

        async def validate_id_token(self, *, id_token: str, nonce: str) -> GoogleIdentity:
            del id_token, nonce
            return identity

    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: FakeGoogle())

    async with anonymous_client() as anonymous:
        start = await anonymous.get("/api/v1/auth/google/start")
        assert start.status_code == 200
        state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
        assert anonymous.cookies.get(OAUTH_COOKIE)
        callback = await anonymous.get(
            "/api/v1/auth/google/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code == 303
        assert callback.headers["location"] == "http://frontend.test/login?oauth=unavailable"
        assert callback.cookies.get(settings.session_cookie_name) is None

    async with session_scope() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == user_id)
            )
            == 0
        )


# --------------------------------------------------------------------------- #
# Honest usage
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def clean_usage(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Usage events outlive the identity cleanup, so this suite starts empty."""

    async with session_scope() as session:
        await session.execute(delete(AIUsageEvent))
        await session.commit()
    yield client


async def _add_usage(
    session: AsyncSession,
    workspace_id: str,
    *,
    capability: str = "text",
    quality: str = "standard",
    cost: Decimal | None,
    currency: str | None,
    tokens: int = 100,
    created_at: datetime | None = None,
) -> None:
    session.add(
        AIUsageEvent(
            workspace_id=workspace_id,
            user_id=None,
            capability=capability,
            quality_level=quality,
            provider="openrouter",
            requested_model="modelo-interno/secreto",
            actual_model="modelo-real/secreto",
            prompt_tokens=tokens // 2,
            completion_tokens=tokens // 2,
            total_tokens=tokens,
            reported_cost=cost,
            currency=currency,
            provider_request_id="req_privado_123",
            outcome="succeeded",
            created_at=created_at or datetime.now(UTC),
        )
    )


@pytest.mark.asyncio
async def test_usage_reports_known_and_unknown_costs_without_inventing_zeros(
    clean_usage: AsyncClient,
) -> None:
    client = clean_usage
    async with session_scope() as session:
        await _add_usage(session, "ws_test_001", cost=Decimal("0.00120000"), currency="USD")
        await _add_usage(session, "ws_test_001", cost=None, currency="USD")
        await _add_usage(
            session, "ws_test_001", capability="image_prompt", quality="high", cost=None, currency=None
        )
        await _add_usage(
            session,
            "ws_test_001",
            cost=Decimal("9.99000000"),
            currency="USD",
            created_at=datetime.now(UTC) - timedelta(days=45),
        )
        await session.commit()

    response = await client.get("/api/v1/auth/usage", headers={"X-Workspace-Id": "ws_test_001"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["period_days"] == 30
    groups = {(item["capability"], item["quality_level"]): item for item in payload["items"]}

    text_group = groups[("text", "standard")]
    assert text_group["generations"] == 2
    assert Decimal(text_group["reported_cost"]) == Decimal("0.00120000")
    assert text_group["known_cost_count"] == 1
    # An unknown cost is never counted as zero.
    assert text_group["unknown_cost_count"] == 1
    assert text_group["currency"] == "USD"

    image_group = groups[("image_prompt", "high")]
    assert image_group["reported_cost"] is None
    assert image_group["known_cost_count"] == 0
    assert image_group["unknown_cost_count"] == 1

    # Older than 30 days is out, and nothing identifies a model or a request.
    assert sum(item["generations"] for item in payload["items"]) == 3
    body = response.text
    for leak in ("modelo-interno", "modelo-real", "req_privado_123", "openrouter"):
        assert leak not in body


@pytest.mark.asyncio
async def test_usage_is_isolated_to_the_authorized_workspace(clean_usage: AsyncClient) -> None:
    client = clean_usage
    async with session_scope() as session:
        session.add(Workspace(id="ws_other_usage", name="Otro workspace"))
        await session.flush()
        await _add_usage(session, "ws_test_001", cost=Decimal("1.00000000"), currency="USD")
        await _add_usage(session, "ws_other_usage", cost=Decimal("50.00000000"), currency="USD")
        await session.commit()

    mine = await client.get("/api/v1/auth/usage", headers={"X-Workspace-Id": "ws_test_001"})
    assert mine.status_code == 200
    assert [Decimal(item["reported_cost"]) for item in mine.json()["items"]] == [Decimal("1")]

    foreign = await client.get(
        "/api/v1/auth/usage", headers={"X-Workspace-Id": "ws_other_usage"}
    )
    assert foreign.status_code == 403


@pytest.mark.asyncio
async def test_usage_is_empty_when_nothing_was_generated(clean_usage: AsyncClient) -> None:
    client = clean_usage
    response = await client.get("/api/v1/auth/usage", headers={"X-Workspace-Id": "ws_test_001"})
    assert response.status_code == 200
    assert response.json() == {"period_days": 30, "items": []}
