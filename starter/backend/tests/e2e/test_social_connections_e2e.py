"""WAVE-012 slice 2: social connections over HTTP and real PostgreSQL.

Every provider used here is either the offline demo provider or an in-process
stub. No test opens an outbound socket or contacts a real social network.
"""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text

from app.core.config import settings
from app.core.cookies import SOCIAL_OAUTH_COOKIE, read_social_oauth_cookie
from app.db.session import get_session_factory
from app.identity.purge import process_available_purge_jobs
from app.main import app
from app.social import crypto, providers

TEST_KEY = base64.b64encode(b"social-token-e2e-key".ljust(32, b"!")).decode("ascii")
CONNECTION_KEYS = frozenset(
    {
        "id",
        "provider",
        "display_name",
        "account_type",
        "status",
        "connected_at",
        "last_checked_at",
        "safe_error",
    }
)


@pytest.fixture
def cipher_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "social_token_encryption_key", TEST_KEY)
    return TEST_KEY


@pytest.fixture
def demo_provider(monkeypatch: pytest.MonkeyPatch, cipher_key: str) -> None:
    """Configure the offline provider and the in-memory handshake store."""

    del cipher_key
    monkeypatch.setattr(settings, "social_connections_enabled", True)
    monkeypatch.setattr(settings, "social_demo_provider_enabled", True)
    monkeypatch.setattr(settings, "redis_provider", "memory")
    monkeypatch.setattr(settings, "social_oauth_state_ttl_seconds", 600)
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")
    monkeypatch.setattr(settings, "social_public_backend_url", "http://api.test")


@dataclass(frozen=True)
class AuthorizationFlow:
    authorization_url: str
    state: str
    cookie: str
    callback_path: str
    authorize_response: Response


class StubSocialProvider:
    """An in-process provider whose account result is controlled by a test."""

    name = "demo"
    supports_pkce = True
    scopes = ("demo_basic",)

    def __init__(self, accounts: tuple[providers.OwnedAccount, ...]) -> None:
        self.accounts = accounts

    def build_authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        del code_challenge
        return f"{redirect_uri}?code=stub-code-{state[:16]}&state={state}"

    async def exchange_authorization_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> providers.ProviderToken:
        del code_verifier, redirect_uri
        return providers.ProviderToken(
            access_token=f"stub-access-{code}",
            refresh_token=None,
            expires_at=datetime.now(UTC) + timedelta(days=30),
            granted_scopes=self.scopes,
        )

    async def resolve_owned_accounts(
        self, *, access_token: str
    ) -> tuple[providers.OwnedAccount, ...]:
        del access_token
        return self.accounts

    async def validate_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> providers.ConnectionCheck:
        del access_token, provider_account_id
        return providers.ConnectionCheck(status="connected")

    async def revoke_connection(self, *, access_token: str, provider_account_id: str) -> bool:
        del access_token, provider_account_id
        return True


def _callback_path(flow: AuthorizationFlow, provider: str = "demo") -> str:
    parsed = urlparse(flow.callback_path)
    return f"/api/v1/social/{provider}/callback?{parsed.query}"


async def _start_authorization(
    client: AsyncClient,
    workspace_id: str,
    *,
    return_path: str = "/settings/connections",
    code_prefix: str = "demo-code-",
) -> AuthorizationFlow:
    response = await client.post(
        "/api/v1/social/demo/authorize",
        json={"return_path": return_path},
        headers={"X-Workspace-Id": workspace_id},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    authorization_url = str(payload["authorization_url"])
    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    state_values = query.get("state")
    assert state_values and len(state_values) == 1
    state = state_values[0]
    cookie = response.cookies.get(SOCIAL_OAUTH_COOKIE)
    assert cookie
    assert read_social_oauth_cookie(cookie) == state
    assert query.get("code") == [f"{code_prefix}{state[:16]}"]
    return AuthorizationFlow(
        authorization_url=authorization_url,
        state=state,
        cookie=cookie,
        callback_path=f"{parsed.path}?{parsed.query}",
        authorize_response=response,
    )


async def _complete_authorization(
    client: AsyncClient,
    flow: AuthorizationFlow,
    *,
    cookie: str | None = None,
    provider: str = "demo",
) -> Response:
    request_cookies = {} if cookie is None else {SOCIAL_OAUTH_COOKIE: cookie}
    return await client.get(
        _callback_path(flow, provider),
        cookies=request_cookies,
        follow_redirects=False,
    )


def _redirect_params(response: Response) -> dict[str, list[str]]:
    assert response.status_code == 303, response.text
    location = response.headers.get("location")
    assert location
    parsed = urlparse(location)
    assert parsed.scheme == "http"
    assert parsed.netloc == "frontend.test"
    return parse_qs(parsed.query)


def _assert_redirect(
    response: Response,
    *,
    outcome: str,
    provider: str,
    reason: str | None = None,
    path: str | None = None,
) -> None:
    params = _redirect_params(response)
    assert params["social"] == [outcome]
    assert params["provider"] == [provider]
    if reason is None:
        assert "reason" not in params
    else:
        assert params["reason"] == [reason]
    if path is not None:
        assert urlparse(response.headers["location"]).path == path


def _raw_rows(engine: object, workspace_id: str) -> list[dict[str, object]]:
    with engine.connect() as connection:  # type: ignore[union-attr]
        return [
            dict(row)
            for row in connection.execute(
                text("SELECT * FROM social_connections WHERE workspace_id = :workspace_id"),
                {"workspace_id": workspace_id},
            ).mappings()
        ]


def _raw_count(engine: object, workspace_id: str) -> int:
    with engine.connect() as connection:  # type: ignore[union-attr]
        return int(
            connection.execute(
                text("SELECT count(*) FROM social_connections WHERE workspace_id = :workspace_id"),
                {"workspace_id": workspace_id},
            ).scalar_one()
        )


def _assert_secret_absent(response: Response, secret: str) -> None:
    assert secret not in response.text
    for header_value in response.headers.values():
        assert secret not in header_value


def _assert_sanitized_connection(connection: dict[str, object]) -> None:
    assert set(connection) == CONNECTION_KEYS
    serialized = json.dumps(connection, ensure_ascii=False).casefold()
    for marker in ("token", "envelope", "scope", "payload", "v1.", "demo-basic"):
        assert marker not in serialized
    assert "demo_basic" not in serialized


def _status_token(seed: str) -> str:
    return (seed * 8)[:43]


# --------------------------------------------------------------------------- #
# Handshake, state and persistence
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_full_social_flow_persists_and_lists_connection(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)

    callback = await _complete_authorization(client, flow, cookie=flow.cookie)
    _assert_redirect(
        callback,
        outcome="connected",
        provider="demo",
        path="/settings/connections",
    )

    listed = await client.get(
        "/api/v1/social/connections", headers={"X-Workspace-Id": workspace_id}
    )
    assert listed.status_code == 200, listed.text
    connections = listed.json()["connections"]
    assert len(connections) == 1
    assert connections[0]["provider"] == "demo"
    assert len(_raw_rows(migrated_database, workspace_id)) == 1
    assert _raw_rows(migrated_database, workspace_id)[0]["id"] == connections[0]["id"]


@pytest.mark.asyncio
async def test_callback_requires_a_matching_signed_cookie(
    client_factory, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    first = await _start_authorization(client, workspace_id)
    second = await _start_authorization(client, workspace_id)

    # A valid cookie for another handshake must not be accepted for this state.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        mismatched = await browser.get(
            first.callback_path,
            cookies={SOCIAL_OAUTH_COOKIE: second.cookie},
            follow_redirects=False,
        )
    _assert_redirect(
        mismatched,
        outcome="error",
        provider="demo",
        reason="invalid_request",
        path="/settings",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        matching = await browser.get(
            first.callback_path,
            cookies={SOCIAL_OAUTH_COOKIE: first.cookie},
            follow_redirects=False,
        )
    _assert_redirect(
        matching,
        outcome="connected",
        provider="demo",
        path="/settings/connections",
    )
    assert read_social_oauth_cookie(first.cookie) == first.state


@pytest.mark.asyncio
async def test_replaying_callback_is_rejected_without_a_second_row(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)

    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as first_browser,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as replay_browser,
    ):
        first = await first_browser.get(
            flow.callback_path,
            cookies={SOCIAL_OAUTH_COOKIE: flow.cookie},
            follow_redirects=False,
        )
        replay = await replay_browser.get(
            flow.callback_path,
            cookies={SOCIAL_OAUTH_COOKIE: flow.cookie},
            follow_redirects=False,
        )
    _assert_redirect(first, outcome="connected", provider="demo")
    _assert_redirect(
        replay,
        outcome="error",
        provider="demo",
        reason="invalid_request",
        path="/settings",
    )
    assert len(_raw_rows(migrated_database, workspace_id)) == 1


@pytest.mark.asyncio
async def test_callback_on_a_different_provider_is_rejected(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        callback = await browser.get(
            _callback_path(flow, "instagram"),
            cookies={SOCIAL_OAUTH_COOKIE: flow.cookie},
            follow_redirects=False,
        )
    _assert_redirect(
        callback,
        outcome="error",
        provider="instagram",
        reason="invalid_request",
        path="/settings",
    )
    assert _raw_count(migrated_database, workspace_id) == 0


@pytest.mark.asyncio
async def test_missing_cookie_does_not_consume_state(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)

    # This ordering matters: an unauthenticated callback must not let an attacker
    # burn the state before the real browser returns with its signed cookie.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        without_cookie = await browser.get(flow.callback_path, follow_redirects=False)
    _assert_redirect(
        without_cookie,
        outcome="error",
        provider="demo",
        reason="invalid_request",
        path="/settings",
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as browser:
        with_cookie = await browser.get(
            flow.callback_path,
            cookies={SOCIAL_OAUTH_COOKIE: flow.cookie},
            follow_redirects=False,
        )
    _assert_redirect(
        with_cookie,
        outcome="connected",
        provider="demo",
        path="/settings/connections",
    )
    assert _raw_count(migrated_database, workspace_id) == 1


# --------------------------------------------------------------------------- #
# Token vault and public response boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_access_token_is_versioned_encrypted_and_round_trips(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)
    callback = await _complete_authorization(client, flow, cookie=flow.cookie)
    _assert_redirect(callback, outcome="connected", provider="demo")

    row = _raw_rows(migrated_database, workspace_id)[0]
    plaintext = f"demo-access-{flow.state[:16]}"
    envelope = str(row["encrypted_access_token"])
    assert envelope.startswith("v1")
    assert envelope != plaintext
    assert (
        crypto.decrypt_token(
            envelope,
            workspace_id=workspace_id,
            provider="demo",
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        )
        == plaintext
    )


@pytest.mark.asyncio
async def test_access_token_plaintext_never_appears_in_sql_or_http(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)
    callback = await _complete_authorization(client, flow, cookie=flow.cookie)
    _assert_redirect(callback, outcome="connected", provider="demo")
    plaintext = f"demo-access-{flow.state[:16]}"

    listed = await client.get(
        "/api/v1/social/connections", headers={"X-Workspace-Id": workspace_id}
    )
    connection_id = listed.json()["connections"][0]["id"]
    checked = await client.post(
        f"/api/v1/social/connections/{connection_id}/check",
        headers={"X-Workspace-Id": workspace_id},
    )
    rows_before_disconnect = _raw_rows(migrated_database, workspace_id)
    assert len(rows_before_disconnect) == 1
    disconnected = await client.delete(
        f"/api/v1/social/connections/{connection_id}",
        headers={"X-Workspace-Id": workspace_id},
    )

    responses = (flow.authorize_response, callback, listed, checked, disconnected)
    for response in responses:
        _assert_secret_absent(response, plaintext)

    for row in rows_before_disconnect:
        for column_value in row.values():
            assert plaintext not in str(column_value)

    rows_after_disconnect = _raw_rows(migrated_database, workspace_id)
    for row in rows_after_disconnect:
        for column_value in row.values():
            assert plaintext not in str(column_value)


@pytest.mark.asyncio
async def test_list_check_disconnect_return_only_sanitized_connection_shape(
    client_factory, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)
    callback = await _complete_authorization(client, flow, cookie=flow.cookie)
    _assert_redirect(callback, outcome="connected", provider="demo")

    listed = await client.get(
        "/api/v1/social/connections", headers={"X-Workspace-Id": workspace_id}
    )
    assert listed.status_code == 200, listed.text
    listed_payload = listed.json()
    assert set(listed_payload) == {"enabled", "providers", "connections"}
    assert len(listed_payload["connections"]) == 1
    _assert_sanitized_connection(listed_payload["connections"][0])
    connection_id = listed_payload["connections"][0]["id"]

    checked = await client.post(
        f"/api/v1/social/connections/{connection_id}/check",
        headers={"X-Workspace-Id": workspace_id},
    )
    assert checked.status_code == 200, checked.text
    checked_connection = checked.json()["connection"]
    _assert_sanitized_connection(checked_connection)
    assert checked_connection["status"] == "connected"

    disconnected = await client.delete(
        f"/api/v1/social/connections/{connection_id}",
        headers={"X-Workspace-Id": workspace_id},
    )
    assert disconnected.status_code == 200, disconnected.text
    disconnected_connection = disconnected.json()["connection"]
    _assert_sanitized_connection(disconnected_connection)
    assert disconnected_connection["status"] == "disconnected"


@pytest.mark.asyncio
async def test_disconnect_is_idempotent_and_second_delete_changes_nothing(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)
    callback = await _complete_authorization(client, flow, cookie=flow.cookie)
    _assert_redirect(callback, outcome="connected", provider="demo")
    listed = await client.get(
        "/api/v1/social/connections", headers={"X-Workspace-Id": workspace_id}
    )
    connection_id = listed.json()["connections"][0]["id"]
    path = f"/api/v1/social/connections/{connection_id}"

    first_delete = await client.delete(path, headers={"X-Workspace-Id": workspace_id})
    second_delete = await client.delete(path, headers={"X-Workspace-Id": workspace_id})
    assert first_delete.status_code == 200, first_delete.text
    assert second_delete.status_code == 200, second_delete.text
    assert second_delete.json() == first_delete.json()
    row = _raw_rows(migrated_database, workspace_id)[0]
    assert row["status"] == "disconnected"
    assert row["encrypted_access_token"] is None
    assert row["encrypted_refresh_token"] is None


# --------------------------------------------------------------------------- #
# Workspace authorization and PostgreSQL concurrency
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_connections_are_isolated_between_workspaces(
    client_factory, demo_provider: None
) -> None:
    del demo_provider
    client_a, workspace_a = await client_factory(workspace_name="Workspace A")
    client_b, workspace_b = await client_factory(workspace_name="Workspace B")
    flow_a = await _start_authorization(client_a, workspace_a)
    flow_b = await _start_authorization(client_b, workspace_b)
    callback_a = await _complete_authorization(client_a, flow_a, cookie=flow_a.cookie)
    callback_b = await _complete_authorization(client_b, flow_b, cookie=flow_b.cookie)
    _assert_redirect(callback_a, outcome="connected", provider="demo")
    _assert_redirect(callback_b, outcome="connected", provider="demo")

    listed_a = await client_a.get(
        "/api/v1/social/connections", headers={"X-Workspace-Id": workspace_a}
    )
    listed_b = await client_b.get(
        "/api/v1/social/connections", headers={"X-Workspace-Id": workspace_b}
    )
    ids_a = {item["id"] for item in listed_a.json()["connections"]}
    ids_b = {item["id"] for item in listed_b.json()["connections"]}
    assert len(ids_a) == 1
    assert len(ids_b) == 1
    assert ids_a.isdisjoint(ids_b)
    assert next(iter(ids_b)) not in ids_a


@pytest.mark.asyncio
async def test_foreign_connection_id_is_indistinguishable_from_missing_id(
    client_factory, demo_provider: None
) -> None:
    del demo_provider
    client_a, workspace_a = await client_factory(workspace_name="Owner")
    client_b, workspace_b = await client_factory(workspace_name="Other")
    flow = await _start_authorization(client_a, workspace_a)
    callback = await _complete_authorization(client_a, flow, cookie=flow.cookie)
    _assert_redirect(callback, outcome="connected", provider="demo")
    connection_id = (
        await client_a.get("/api/v1/social/connections", headers={"X-Workspace-Id": workspace_a})
    ).json()["connections"][0]["id"]
    headers = {"X-Workspace-Id": workspace_b}

    foreign_check = await client_b.post(
        f"/api/v1/social/connections/{connection_id}/check", headers=headers
    )
    missing_check = await client_b.post(
        "/api/v1/social/connections/nonexistent-social-id/check", headers=headers
    )
    assert foreign_check.status_code == 404
    assert missing_check.status_code == 404
    assert foreign_check.json() == missing_check.json()

    foreign_delete = await client_b.delete(
        f"/api/v1/social/connections/{connection_id}", headers=headers
    )
    missing_delete = await client_b.delete(
        "/api/v1/social/connections/nonexistent-social-id", headers=headers
    )
    assert foreign_delete.status_code == 404
    assert missing_delete.status_code == 404
    assert foreign_delete.json() == missing_delete.json()


@pytest.mark.asyncio
async def test_two_callbacks_for_the_same_state_have_one_winner(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id)

    # Both requests must contend through the real callback route. The state
    # lease, not a test-only consume call, decides which request may persist.
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as first_browser,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second_browser,
    ):
        first, second = await asyncio.gather(
            first_browser.get(
                flow.callback_path,
                cookies={SOCIAL_OAUTH_COOKIE: flow.cookie},
                follow_redirects=False,
            ),
            second_browser.get(
                flow.callback_path,
                cookies={SOCIAL_OAUTH_COOKIE: flow.cookie},
                follow_redirects=False,
            ),
        )
    responses = (first, second)
    for response in responses:
        assert response.status_code == 303
        params = _redirect_params(response)
        assert params["provider"] == ["demo"]
    assert sum(_redirect_params(response)["social"] == ["connected"] for response in responses) == 1
    assert (
        sum(
            _redirect_params(response).get("reason") == ["invalid_request"]
            for response in responses
        )
        == 1
    )
    assert len(_raw_rows(migrated_database, workspace_id)) == 1


@pytest.mark.asyncio
async def test_independent_authorizations_for_one_account_are_one_postgres_row(
    client_factory, migrated_database, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    fixed_account = providers.OwnedAccount(
        provider_account_id="fixed-provider-account",
        display_name="cuenta.fija",
        account_type="business",
    )
    stub = StubSocialProvider(accounts=(fixed_account,))
    monkeypatch.setattr(providers, "build_provider", lambda name: stub)

    client, workspace_id = await client_factory()
    first = await _start_authorization(client, workspace_id, code_prefix="stub-code-")
    second = await _start_authorization(client, workspace_id, code_prefix="stub-code-")
    async with (
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as first_browser,
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as second_browser,
    ):
        first_response, second_response = await asyncio.gather(
            first_browser.get(
                first.callback_path,
                cookies={SOCIAL_OAUTH_COOKIE: first.cookie},
                follow_redirects=False,
            ),
            second_browser.get(
                second.callback_path,
                cookies={SOCIAL_OAUTH_COOKIE: second.cookie},
                follow_redirects=False,
            ),
        )

    # Independent handshakes can both miss the fast-path SELECT. PostgreSQL's
    # unique constraint and savepoint path must converge them without a 500.
    assert first_response.status_code == 303
    assert second_response.status_code == 303
    assert first_response.status_code < 500
    assert second_response.status_code < 500
    _assert_redirect(first_response, outcome="connected", provider="demo")
    _assert_redirect(second_response, outcome="connected", provider="demo")
    rows = _raw_rows(migrated_database, workspace_id)
    assert len(rows) == 1
    assert rows[0]["provider_account_id"] == fixed_account.provider_account_id


# --------------------------------------------------------------------------- #
# Deletion, provider safety and publish-surface guard
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_workspace_cascade_and_durable_account_purge_remove_connections(
    client_factory, migrated_database, demo_provider: None
) -> None:
    del demo_provider
    cascade_client, cascade_workspace = await client_factory(workspace_name="Cascade")
    cascade_flow = await _start_authorization(cascade_client, cascade_workspace)
    cascade_callback = await _complete_authorization(
        cascade_client, cascade_flow, cookie=cascade_flow.cookie
    )
    _assert_redirect(cascade_callback, outcome="connected", provider="demo")
    assert _raw_count(migrated_database, cascade_workspace) == 1

    # This is the database-level FK cascade, separate from the worker's explicit
    # purge statement. It must destroy the credential row with its workspace.
    with migrated_database.begin() as connection:
        connection.execute(
            text("DELETE FROM workspaces WHERE id = :workspace_id"),
            {"workspace_id": cascade_workspace},
        )
    assert _raw_count(migrated_database, cascade_workspace) == 0

    purge_client, purge_workspace = await client_factory(workspace_name="Purge")
    purge_flow = await _start_authorization(purge_client, purge_workspace)
    purge_callback = await _complete_authorization(
        purge_client, purge_flow, cookie=purge_flow.cookie
    )
    _assert_redirect(purge_callback, outcome="connected", provider="demo")
    assert _raw_count(migrated_database, purge_workspace) == 1
    deletion = await purge_client.post(
        "/api/v1/auth/account/delete",
        json={
            "confirmation": "ELIMINAR",
            "status_token": _status_token(uuid.uuid4().hex),
        },
    )
    assert deletion.status_code == 202, deletion.text

    async with get_session_factory()() as db:
        processed = await process_available_purge_jobs(db)
    assert processed >= 1
    assert _raw_count(migrated_database, purge_workspace) == 0


@pytest.mark.asyncio
async def test_provider_returning_multiple_accounts_is_rejected_without_rows(
    client_factory, migrated_database, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    stub = StubSocialProvider(
        accounts=(
            providers.OwnedAccount("account-one", "cuenta.uno", "business"),
            providers.OwnedAccount("account-two", "cuenta.dos", "business"),
        )
    )
    monkeypatch.setattr(providers, "build_provider", lambda name: stub)
    client, workspace_id = await client_factory()
    flow = await _start_authorization(client, workspace_id, code_prefix="stub-code-")

    # Choosing one account silently would connect the wrong identity. WAVE-012
    # has no selection UI, so the safe result is a neutral provider error.
    callback = await _complete_authorization(client, flow, cookie=flow.cookie)
    _assert_redirect(
        callback,
        outcome="error",
        provider="demo",
        reason="provider_error",
        path="/settings/connections",
    )
    assert _raw_count(migrated_database, workspace_id) == 0


@pytest.mark.asyncio
async def test_social_surface_has_no_publish_route(client_factory, demo_provider: None) -> None:
    del demo_provider
    client, workspace_id = await client_factory()
    paths = app.openapi()["paths"]
    social_paths = [path for path in paths if path.startswith(f"{settings.api_prefix}/social")]
    assert social_paths
    assert not any(
        marker in path.casefold() for path in social_paths for marker in ("publish", "post")
    )

    headers = {"X-Workspace-Id": workspace_id}
    for method in ("post", "put"):
        for path in (
            "/api/v1/social/connections/not-a-connection/publish",
            "/api/v1/social/publish",
        ):
            response = await getattr(client, method)(path, headers=headers)
            assert response.status_code in {404, 405}
