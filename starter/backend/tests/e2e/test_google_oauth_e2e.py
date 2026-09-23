from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.core.cookies import OAUTH_COOKIE as GOOGLE_OAUTH_COOKIE_NAME
from app.db.session import get_session_factory
from app.identity.google_oauth import GoogleIdentity
from app.identity.models import OAuthAccount, PendingSignup


class DeterministicGoogleOIDCClient:
    def __init__(self, identity: GoogleIdentity) -> None:
        self.identity = identity

    def authorization_url(self, **kwargs: str) -> str:
        return f"https://accounts.google.com/mock?state={kwargs['state']}"

    async def exchange_code(self, *, code: str, code_verifier: str) -> str:
        assert code and code_verifier
        return "deterministic-id-token"

    async def validate_id_token(self, *, id_token: str, nonce: str) -> GoogleIdentity:
        assert id_token == "deterministic-id-token"
        assert nonce
        return self.identity


@pytest.fixture
def configured_google(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_sign_in_enabled", True)
    monkeypatch.setattr(settings, "google_client_id", "e2e-google-client")
    monkeypatch.setattr(settings, "google_client_secret", "e2e-google-secret")
    monkeypatch.setattr(settings, "google_redirect_uri", "http://test/api/v1/auth/google/callback")
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")


async def _start(client: AsyncClient) -> tuple[str, str]:
    response = await client.get("/api/v1/auth/google/start")
    assert response.status_code == 200, response.text
    state = parse_qs(urlparse(response.json()["authorization_url"]).query)["state"][0]
    cookie = response.cookies.get(GOOGLE_OAUTH_COOKIE_NAME)
    assert cookie
    return state, cookie


@pytest.mark.asyncio
async def test_google_signup_completes_over_http_against_postgres(
    e2e_database: None, configured_google: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del e2e_database
    identity = GoogleIdentity("google-e2e-subject", "google-e2e@example.com", "Google E2E")
    monkeypatch.setattr(
        "app.identity.routes.get_google_oidc_client", lambda: DeterministicGoogleOIDCClient(identity)
    )
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        state, _ = await _start(client)
        callback = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "code", "state": state},
            follow_redirects=False,
        )
        assert callback.headers["location"] == "http://frontend.test/onboarding"
        version = (await client.get("/api/v1/auth/signup")).json()["signup"]["version"]
        for step, payload in (
            ("business", {
                "name": "Café OAuth E2E", "category": "gastronomy", "country": "Honduras",
                "city": "Tegucigalpa", "primary_product": "Café", "target_audience": "Clientes",
            }),
            ("channels", {"preferred_platforms": ["instagram"], "primary_objective": "sales"}),
            ("brand", {"voice_tones": ["friendly"], "value_proposition": "Café", "content_locale": "es"}),
            ("review", {"confirmed": True}),
        ):
            saved = await client.patch(
                "/api/v1/auth/signup",
                json={"step": step, "expected_version": version, step: payload},
            )
            assert saved.status_code == 200, saved.text
            version = saved.json()["signup"]["version"]
        completed = await client.post(
            "/api/v1/auth/signup/complete", headers={"Idempotency-Key": "google-e2e-complete"}
        )
        assert completed.status_code == 200, completed.text
        assert (await client.get("/api/v1/auth/me")).status_code == 200

    async with get_session_factory()() as session:
        account = (
            await session.execute(
                select(OAuthAccount).where(OAuthAccount.provider_subject == identity.subject)
            )
        ).scalar_one()
        assert account.email_at_link_time == identity.email


@pytest.mark.asyncio
async def test_concurrent_google_callbacks_create_one_pending_signup(
    e2e_database: None, configured_google: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del e2e_database
    identity = GoogleIdentity("google-e2e-concurrent", "google-concurrent@example.com", "Concurrent")
    monkeypatch.setattr(
        "app.identity.routes.get_google_oidc_client", lambda: DeterministicGoogleOIDCClient(identity)
    )
    from app.main import app

    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as first,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second,
    ):
        first_state, first_cookie = await _start(first)
        second_state, second_cookie = await _start(second)
        first.cookies.set(GOOGLE_OAUTH_COOKIE_NAME, first_cookie, path="/api/v1/auth/google")
        second.cookies.set(GOOGLE_OAUTH_COOKIE_NAME, second_cookie, path="/api/v1/auth/google")
        first_response, second_response = await asyncio.gather(
            first.get(
                "/api/v1/auth/google/callback",
                params={"code": "first", "state": first_state},
                follow_redirects=False,
            ),
            second.get(
                "/api/v1/auth/google/callback",
                params={"code": "second", "state": second_state},
                follow_redirects=False,
            ),
        )
    assert first_response.headers["location"] == "http://frontend.test/onboarding"
    assert second_response.headers["location"] == "http://frontend.test/onboarding"
    async with get_session_factory()() as session:
        records = (
            await session.execute(
                select(PendingSignup).where(PendingSignup.oauth_subject == identity.subject)
            )
        ).scalars().all()
        assert len(records) == 1
