from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import Settings, settings
from app.core.cookies import OAUTH_COOKIE as GOOGLE_OAUTH_COOKIE_NAME
from app.core.cookies import SIGNUP_COOKIE as SIGNUP_COOKIE_NAME
from app.core.errors import AppError
from app.dependencies import get_db
from app.identity.google_oauth import GoogleIdentity, GoogleOIDCClient, GoogleOIDCError
from app.identity.models import OAuthAccount, OAuthAuthorizationRequest, PendingSignup, User


class FakeGoogleOIDCClient:
    def __init__(self, identity: GoogleIdentity) -> None:
        self.identity = identity
        self.authorization_calls: list[dict[str, str]] = []
        self.exchange_error: GoogleOIDCError | None = None
        self.validation_error: GoogleOIDCError | None = None

    def authorization_url(self, **kwargs: str) -> str:
        self.authorization_calls.append(kwargs)
        return f"https://accounts.google.com/mock-authorize?{urlencode(kwargs)}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> str:
        assert code
        assert code_verifier
        if self.exchange_error:
            raise self.exchange_error
        return "fake-id-token"

    async def validate_id_token(self, *, id_token: str, nonce: str) -> GoogleIdentity:
        assert id_token == "fake-id-token"
        assert nonce
        if self.validation_error:
            raise self.validation_error
        return self.identity


@pytest.fixture
def google_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_sign_in_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", "google-client-id")
    monkeypatch.setattr(settings, "google_client_secret", "google-client-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://test/api/v1/auth/google/callback")
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")
    monkeypatch.setattr(settings, "google_oauth_state_ttl_seconds", 600)


async def _db_session():
    from app.main import app

    async for session in app.dependency_overrides[get_db]():
        yield session


async def _google_start(client: AsyncClient) -> tuple[str, str]:
    response = await client.get("/api/v1/auth/google/start")
    assert response.status_code == 200, response.text
    state = parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]
    oauth_cookie = response.cookies.get(GOOGLE_OAUTH_COOKIE_NAME)
    assert oauth_cookie
    return state, oauth_cookie


def _fake_client(identity: GoogleIdentity) -> FakeGoogleOIDCClient:
    return FakeGoogleOIDCClient(identity)


def test_google_configuration_rejects_a_frontend_outside_allowed_origins() -> None:
    config = Settings(
        {
            "APP_ENV": "test",
            "ALLOWED_ORIGINS": "http://frontend.test",
            "FRONTEND_URL": "http://unexpected.test",
            "GOOGLE_SIGN_IN_ENABLED": "1",
            "GOOGLE_CLIENT_ID": "google-client-id",
            "GOOGLE_CLIENT_SECRET": "secret",
            "GOOGLE_REDIRECT_URI": "http://api.test/api/v1/auth/google/callback",
        }
    )
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        config.validate_runtime_configuration()


@pytest.mark.asyncio
async def test_google_start_creates_state_pkce_cookie_and_minimal_scope(
    client: AsyncClient, google_config: None
) -> None:
    response = await client.get("/api/v1/auth/google/start")
    assert response.status_code == 200
    query = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert query["response_type"] == ["code"]
    assert query["scope"] == ["openid email profile"]
    assert query["code_challenge_method"] == ["S256"]
    assert len(query["state"][0]) >= 32
    assert "code_verifier" not in query
    cookie = response.headers["set-cookie"].casefold()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "secure" not in cookie
    assert response.headers["cache-control"] == "no-store"

    async for session in _db_session():
        stored = (
            await session.execute(select(OAuthAuthorizationRequest))
        ).scalar_one()
        assert stored.state_hash != query["state"][0]
        assert stored.consumed_at is None


@pytest.mark.asyncio
async def test_google_start_is_safely_unavailable_without_credentials(client: AsyncClient) -> None:
    previous_enabled = settings.google_sign_in_enabled
    previous_client_id = settings.google_client_id
    previous_secret = settings.google_client_secret
    try:
        settings.google_sign_in_enabled = False
        settings.google_client_id = ""
        settings.google_client_secret = ""
        status = await client.get("/api/v1/auth/google/status")
        assert status.json() == {"configured": False}
        start = await client.get("/api/v1/auth/google/start")
        assert start.status_code == 503
        assert start.json()["error"]["code"] == "GOOGLE_SIGN_IN_UNAVAILABLE"
    finally:
        settings.google_sign_in_enabled = previous_enabled
        settings.google_client_id = previous_client_id
        settings.google_client_secret = previous_secret


@pytest.mark.asyncio
async def test_valid_google_callback_creates_pending_signup_and_requires_onboarding(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    fake = _fake_client(GoogleIdentity("google-sub-1", "ana.google@example.com", "Ana Google"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    state, _ = await _google_start(client)

    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code-1", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "http://frontend.test/onboarding"
    assert callback.headers["cache-control"] == "no-store"
    assert callback.cookies.get(SIGNUP_COOKIE_NAME)
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    signup = await client.get("/api/v1/auth/signup")
    assert signup.status_code == 200
    assert signup.json()["signup"]["current_step"] == "business"

    async for session in _db_session():
        pending = (
            await session.execute(
                select(PendingSignup).where(PendingSignup.oauth_subject == "google-sub-1")
            )
        ).scalar_one()
        assert pending.password_hash is None
        assert pending.oauth_provider == "google"
        assert (
            await session.execute(select(User).where(User.email == "ana.google@example.com"))
        ).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_google_callback_rejects_invalid_expired_and_reused_state(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    fake = _fake_client(GoogleIdentity("google-sub-state", "state@example.com", "State"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    state, cookie = await _google_start(client)

    invalid = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": "invalid"},
        follow_redirects=False,
    )
    assert invalid.headers["location"] == "http://frontend.test/login?oauth=invalid_state"

    async for session in _db_session():
        request = (
            await session.execute(select(OAuthAuthorizationRequest))
        ).scalar_one()
        request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    client.cookies.set(GOOGLE_OAUTH_COOKIE_NAME, cookie, path="/api/v1/auth/google")
    expired = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert expired.headers["location"] == "http://frontend.test/login?oauth=expired_state"

    state, cookie = await _google_start(client)
    first = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert first.headers["location"] == "http://frontend.test/onboarding"
    client.cookies.set(
        GOOGLE_OAUTH_COOKIE_NAME,
        cookie,
        path="/api/v1/auth/google",
    )
    replay = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert replay.headers["location"] == "http://frontend.test/login?oauth=used_state"


@pytest.mark.asyncio
async def test_google_callback_logs_in_an_existing_linked_identity(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    async for session in _db_session():
        user = User(email="linked@example.com", name="Linked", password_hash="")
        session.add(user)
        await session.flush()
        session.add(
            OAuthAccount(
                user_id=user.id,
                provider="google",
                provider_subject="google-linked",
                email_at_link_time=user.email,
            )
        )
        await session.commit()
    fake = _fake_client(GoogleIdentity("google-linked", "linked@example.com", "Linked"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    state, _ = await _google_start(client)
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert callback.headers["location"] == "http://frontend.test/dashboard"
    assert callback.cookies.get(settings.session_cookie_name)
    assert (await client.get("/api/v1/auth/me")).status_code == 200


@pytest.mark.asyncio
async def test_google_callback_does_not_link_a_password_account_by_email(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    async for session in _db_session():
        session.add(User(email="password@example.com", name="Password", password_hash="scrypt$00$00"))
        await session.commit()
    fake = _fake_client(GoogleIdentity("google-new", "password@example.com", "Password"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    state, _ = await _google_start(client)
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state, "next": "https://evil.example"},
        follow_redirects=False,
    )
    assert callback.headers["location"] == "http://frontend.test/login?oauth=account_exists"
    assert "evil.example" not in callback.headers["location"]
    async for session in _db_session():
        assert (await session.execute(select(OAuthAccount))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_google_signup_completion_creates_oauth_account_atomically(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    fake = _fake_client(GoogleIdentity("google-complete", "complete.google@example.com", "Complete"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    state, _ = await _google_start(client)
    callback = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303
    version = (await client.get("/api/v1/auth/signup")).json()["signup"]["version"]
    drafts = (
        ("business", {
            "name": "Café Google", "category": "gastronomy", "country": "Honduras",
            "city": "Tegucigalpa", "primary_product": "Café", "target_audience": "Clientes",
        }),
        ("channels", {"preferred_platforms": ["instagram"], "primary_objective": "sales"}),
        ("brand", {"voice_tones": ["friendly"], "value_proposition": "Café local", "content_locale": "es"}),
        ("review", {"confirmed": True}),
    )
    for step, payload in drafts:
        saved = await client.patch(
            "/api/v1/auth/signup",
            json={"step": step, "expected_version": version, step: payload},
        )
        assert saved.status_code == 200, saved.text
        version = saved.json()["signup"]["version"]
    complete = await client.post(
        "/api/v1/auth/signup/complete", headers={"Idempotency-Key": "google-complete"}
    )
    assert complete.status_code == 200
    async for session in _db_session():
        account = (
            await session.execute(
                select(OAuthAccount).where(OAuthAccount.provider_subject == "google-complete")
            )
        ).scalar_one()
        assert account.email_at_link_time == "complete.google@example.com"


@pytest.mark.asyncio
async def test_google_signup_completion_rolls_back_oauth_account(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    fake = _fake_client(GoogleIdentity("google-rollback", "rollback.google@example.com", "Rollback"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    state, _ = await _google_start(client)
    await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    version = (await client.get("/api/v1/auth/signup")).json()["signup"]["version"]
    for step, payload in (
        ("business", {
            "name": "Café", "category": "gastronomy", "country": "Honduras", "city": "Tegucigalpa",
            "primary_product": "Café", "target_audience": "Clientes",
        }),
        ("channels", {"preferred_platforms": ["instagram"], "primary_objective": "sales"}),
        ("brand", {"voice_tones": ["friendly"], "value_proposition": "Café", "content_locale": "es"}),
        ("review", {"confirmed": True}),
    ):
        saved = await client.patch(
            "/api/v1/auth/signup",
            json={"step": step, "expected_version": version, step: payload},
        )
        version = saved.json()["signup"]["version"]

    async def fail_business(*args, **kwargs):
        del args, kwargs
        raise AppError("BUSINESS_CREATION_FAILED", "No se pudo crear el negocio.", status_code=500)

    monkeypatch.setattr("app.identity.routes.create_business", fail_business)
    failed = await client.post(
        "/api/v1/auth/signup/complete", headers={"Idempotency-Key": "google-rollback"}
    )
    assert failed.status_code == 500
    async for session in _db_session():
        assert (
            await session.execute(
                select(OAuthAccount).where(OAuthAccount.provider_subject == "google-rollback")
            )
        ).scalar_one_or_none() is None
        assert (
            await session.execute(select(User).where(User.email == "rollback.google@example.com"))
        ).scalar_one_or_none() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("claim", "value", "expected_code"),
    [
        ("iss", "https://issuer.invalid", "GOOGLE_OAUTH_TOKEN_INVALID"),
        ("aud", "other-client", "GOOGLE_OAUTH_TOKEN_INVALID"),
        ("exp", datetime.now(UTC) - timedelta(minutes=1), "GOOGLE_OAUTH_TOKEN_INVALID"),
        ("email_verified", False, "GOOGLE_OAUTH_EMAIL_UNVERIFIED"),
    ],
)
async def test_google_id_token_claim_validation(
    claim: str, value: object, expected_code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Settings(
        {
            "APP_ENV": "test",
            "GOOGLE_SIGN_IN_ENABLED": "1",
            "GOOGLE_CLIENT_ID": "google-client-id",
            "GOOGLE_CLIENT_SECRET": "secret",
            "GOOGLE_REDIRECT_URI": "http://test/callback",
        }
    )
    oidc = GoogleOIDCClient(config)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = "test-key"
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://accounts.google.com",
        "aud": "google-client-id",
        "sub": "google-subject",
        "email": "verified@example.com",
        "email_verified": True,
        "nonce": "nonce-1",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims[claim] = value
    id_token = jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})

    async def fake_jwks() -> dict[str, object]:
        return {"keys": [jwk]}

    monkeypatch.setattr(oidc, "fetch_jwks", fake_jwks)
    with pytest.raises(GoogleOIDCError) as exc_info:
        await oidc.validate_id_token(id_token=id_token, nonce="nonce-1")
    assert exc_info.value.code == expected_code


@pytest.mark.asyncio
async def test_google_pending_signup_concurrency_keeps_one_identity(
    client: AsyncClient, google_config: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.cookies.delete(settings.session_cookie_name)
    fake = _fake_client(GoogleIdentity("google-concurrent", "concurrent@example.com", "Concurrent"))
    monkeypatch.setattr("app.identity.routes.get_google_oidc_client", lambda: fake)
    first_state, first_cookie = await _google_start(client)

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second_client:
        second_state, second_cookie = await _google_start(second_client)
        client.cookies.set(GOOGLE_OAUTH_COOKIE_NAME, first_cookie, path="/api/v1/auth/google")
        second_client.cookies.set(
            GOOGLE_OAUTH_COOKIE_NAME, second_cookie, path="/api/v1/auth/google"
        )
        first, second = await asyncio.gather(
            client.get(
                "/api/v1/auth/google/callback",
                params={"code": "code-1", "state": first_state},
                follow_redirects=False,
            ),
            second_client.get(
                "/api/v1/auth/google/callback",
                params={"code": "code-2", "state": second_state},
                follow_redirects=False,
            ),
        )
    assert {first.status_code, second.status_code} == {303}
    async for session in _db_session():
        pending = (
            await session.execute(
                select(PendingSignup).where(PendingSignup.oauth_subject == "google-concurrent")
            )
        ).scalars().all()
        assert len(pending) == 1
