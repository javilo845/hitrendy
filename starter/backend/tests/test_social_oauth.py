"""Unit tests for the mechanics behind a social connection.

Configuration, the token cipher, the single-use handshake, the redirect guard,
the provider factory and error sanitization. Nothing here touches a network:
the only provider that answers is either the offline demo one or an
``httpx.MockTransport`` that never opens a socket.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, settings
from app.core.cookies import read_social_oauth_cookie, set_social_oauth_cookie
from app.core.ephemeral_store import EphemeralStore, get_ephemeral_store
from app.core.errors import NotFoundError
from app.identity.models import Workspace
from app.social import crypto, oauth_state, providers, service
from app.social.models import SocialConnection

#: Real 32 byte keys, base64 encoded. Deterministic so a failure is
#: reproducible, padded rather than hand-counted, and worthless outside this file.
TEST_KEY = base64.b64encode(b"social-token-test-key".ljust(32, b"!")).decode("ascii")
ROTATED_KEY = base64.b64encode(b"rotated-social-token-key".ljust(32, b"?")).decode("ascii")

WORKSPACE = "ws_crypto_001"
OTHER_WORKSPACE = "ws_crypto_002"


def _development_values(**overrides: str) -> dict[str, str]:
    """A development configuration with social connections switched on."""

    values = {
        "APP_ENV": "development",
        "SOCIAL_CONNECTIONS_ENABLED": "1",
        "SOCIAL_DEMO_PROVIDER_ENABLED": "1",
        "SOCIAL_TOKEN_ENCRYPTION_KEY": TEST_KEY,
        "REDIS_PROVIDER": "memory",
    }
    values.update(overrides)
    return values


def _production_values(**overrides: str) -> dict[str, str]:
    """A production configuration that is valid except for what a test breaks."""

    values = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://app:password@db.example.com/hitrendy",
        "DATABASE_SSL_MODE": "require",
        "REDIS_PROVIDER": "redis",
        "REDIS_URL": "redis://redis:6379/0",
        "STORAGE_PROVIDER": "s3",
        "OBJECT_STORAGE_ENDPOINT": "https://s3.example.com",
        "OBJECT_STORAGE_ACCESS_KEY": "ak",
        "OBJECT_STORAGE_SECRET_KEY": "sk",
        "OBJECT_STORAGE_BUCKET": "bucket",
        "AI_PROVIDER": "openai-compatible",
        "AI_BASE_URL": "https://openrouter.ai/api/v1",
        "AI_API_KEY": "ai-key",
        "AI_MODEL": "approved-model",
        "JWT_SECRET": "j" * 32,
        "ALLOWED_ORIGINS": "https://app.example.com",
        "ALLOWED_HOSTS": "api.example.com",
        "FRONTEND_URL": "https://app.example.com",
        "SOCIAL_CONNECTIONS_ENABLED": "1",
        "SOCIAL_TOKEN_ENCRYPTION_KEY": TEST_KEY,
        "SOCIAL_PUBLIC_BACKEND_URL": "https://api.example.com",
        "INSTAGRAM_CONNECTIONS_ENABLED": "1",
        "INSTAGRAM_CLIENT_ID": "ig-client-id",
        "INSTAGRAM_CLIENT_SECRET": "ig-client-secret",
        "INSTAGRAM_REDIRECT_URI": "https://api.example.com/api/v1/social/instagram/callback",
    }
    values.update(overrides)
    return values


@pytest.fixture
def cipher_key(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "social_token_encryption_key", TEST_KEY)
    return TEST_KEY


@pytest.fixture
def demo_provider(monkeypatch: pytest.MonkeyPatch, cipher_key: str) -> None:
    """The offline provider, configured, with a memory-backed state store."""

    del cipher_key
    monkeypatch.setattr(settings, "social_connections_enabled", True)
    monkeypatch.setattr(settings, "social_demo_provider_enabled", True)
    monkeypatch.setattr(settings, "redis_provider", "memory")
    monkeypatch.setattr(settings, "social_oauth_state_ttl_seconds", 600)
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")
    monkeypatch.setattr(settings, "social_public_backend_url", "http://api.test")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def test_development_configuration_with_the_demo_provider_is_valid() -> None:
    config = Settings(_development_values())
    config.validate_runtime_configuration()
    assert config.social_demo_provider_configured is True
    assert config.social_connections_configured is True


def test_social_connections_refuse_to_start_without_an_encryption_key() -> None:
    config = Settings(_development_values(SOCIAL_TOKEN_ENCRYPTION_KEY=""))
    with pytest.raises(RuntimeError, match="SOCIAL_TOKEN_ENCRYPTION_KEY"):
        config.validate_runtime_configuration()


@pytest.mark.parametrize(
    "key",
    [
        # A password. Human-chosen strings do not decode to 32 bytes, which is
        # exactly why reusing one as a cipher key is rejected at boot.
        "instagram-client-secret",
        # Valid base64, wrong length.
        base64.b64encode(b"too-short").decode("ascii"),
        base64.b64encode(b"x" * 64).decode("ascii"),
        "not base64 at all!!",
    ],
)
def test_encryption_key_rejects_anything_that_is_not_32_random_bytes(key: str) -> None:
    config = Settings(_development_values(SOCIAL_TOKEN_ENCRYPTION_KEY=key))
    with pytest.raises(RuntimeError, match="SOCIAL_TOKEN_ENCRYPTION_KEY"):
        config.validate_runtime_configuration()


def test_social_connections_require_a_state_store() -> None:
    config = Settings(_development_values(REDIS_PROVIDER="disabled"))
    with pytest.raises(RuntimeError, match="REDIS_PROVIDER"):
        config.validate_runtime_configuration()


def test_social_connections_require_the_frontend_to_be_an_allowed_origin() -> None:
    config = Settings(
        _development_values(
            ALLOWED_ORIGINS="http://localhost:3000",
            FRONTEND_URL="http://unexpected.test",
        )
    )
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        config.validate_runtime_configuration()


def test_production_valid_social_configuration() -> None:
    config = Settings(_production_values())
    config.validate_runtime_configuration()
    assert config.instagram_connections_configured is True
    assert config.social_demo_provider_configured is False


def test_production_refuses_the_demo_provider() -> None:
    config = Settings(_production_values(SOCIAL_DEMO_PROVIDER_ENABLED="1"))
    with pytest.raises(RuntimeError, match="SOCIAL_DEMO_PROVIDER_ENABLED"):
        config.validate_runtime_configuration()


def test_staging_refuses_the_demo_provider() -> None:
    config = Settings(_production_values(APP_ENV="staging", SOCIAL_DEMO_PROVIDER_ENABLED="1"))
    with pytest.raises(RuntimeError, match="SOCIAL_DEMO_PROVIDER_ENABLED"):
        config.validate_runtime_configuration()


def test_production_requires_at_least_one_real_provider() -> None:
    config = Settings(_production_values(INSTAGRAM_CONNECTIONS_ENABLED="0"))
    with pytest.raises(RuntimeError, match="proveedor real"):
        config.validate_runtime_configuration()


def test_production_requires_distributed_state() -> None:
    """One instance must be able to finish a handshake another one started."""

    config = Settings(
        _production_values(REDIS_PROVIDER="memory", REDIS_URL="", REDIS_REQUIRED="0")
    )
    with pytest.raises(RuntimeError, match="REDIS_PROVIDER=redis en staging y producción"):
        config.validate_runtime_configuration()


def test_production_rejects_an_http_redirect_uri() -> None:
    config = Settings(
        _production_values(
            SOCIAL_PUBLIC_BACKEND_URL="http://api.example.com",
            INSTAGRAM_REDIRECT_URI="http://api.example.com/api/v1/social/instagram/callback",
        )
    )
    with pytest.raises(RuntimeError, match="SOCIAL_PUBLIC_BACKEND_URL"):
        config.validate_runtime_configuration()


def test_instagram_requires_both_halves_of_its_credential() -> None:
    config = Settings(_production_values(INSTAGRAM_CLIENT_SECRET=""))
    with pytest.raises(RuntimeError, match="INSTAGRAM_CLIENT_SECRET"):
        config.validate_runtime_configuration()


def test_instagram_redirect_uri_must_live_under_the_public_backend() -> None:
    config = Settings(
        _production_values(
            INSTAGRAM_REDIRECT_URI="https://attacker.example.com/api/v1/social/instagram/callback"
        )
    )
    with pytest.raises(RuntimeError, match="INSTAGRAM_REDIRECT_URI"):
        config.validate_runtime_configuration()


def test_a_provider_without_credentials_is_unconfigured_not_enabled() -> None:
    config = Settings(
        _development_values(
            SOCIAL_DEMO_PROVIDER_ENABLED="0",
            INSTAGRAM_CONNECTIONS_ENABLED="1",
        )
    )
    config.validate_runtime_configuration()
    assert config.instagram_connections_configured is False
    assert config.social_connections_configured is False


# --------------------------------------------------------------------------- #
# Token encryption
# --------------------------------------------------------------------------- #


def test_a_token_survives_a_round_trip_and_is_absent_from_its_envelope(cipher_key: str) -> None:
    del cipher_key
    token = "ig-access-token-do-not-echo"
    envelope = crypto.encrypt_token(
        token, workspace_id=WORKSPACE, provider="instagram", purpose=crypto.ACCESS_TOKEN_PURPOSE
    )
    assert token not in envelope
    assert envelope.startswith(f"{crypto.ENVELOPE_VERSION}.")
    assert len(envelope.split(".")) == 3
    assert (
        crypto.decrypt_token(
            envelope,
            workspace_id=WORKSPACE,
            provider="instagram",
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        )
        == token
    )


def test_the_same_token_encrypts_to_different_bytes_every_time(cipher_key: str) -> None:
    del cipher_key
    first, second = (
        crypto.encrypt_token(
            "same-token",
            workspace_id=WORKSPACE,
            provider="instagram",
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        )
        for _ in range(2)
    )
    # Otherwise the rows themselves would reveal that two workspaces connected
    # the same account.
    assert first != second


def test_a_tampered_envelope_is_rejected(cipher_key: str) -> None:
    del cipher_key
    envelope = crypto.encrypt_token(
        "authentic-token",
        workspace_id=WORKSPACE,
        provider="instagram",
        purpose=crypto.ACCESS_TOKEN_PURPOSE,
    )
    version, nonce, ciphertext = envelope.split(".")
    flipped = "B" if ciphertext[0] != "B" else "C"
    for broken in (
        f"{version}.{nonce}.{flipped}{ciphertext[1:]}",
        f"{version}.{nonce}.{ciphertext[:-1]}",
        f"{version}.{'A' * len(nonce)}.{ciphertext}",
        f"v2.{nonce}.{ciphertext}",
        f"{version}.{ciphertext}",
        "",
        "not-an-envelope",
    ):
        with pytest.raises(crypto.TokenDecryptionError):
            crypto.decrypt_token(
                broken,
                workspace_id=WORKSPACE,
                provider="instagram",
                purpose=crypto.ACCESS_TOKEN_PURPOSE,
            )


@pytest.mark.parametrize(
    ("workspace_id", "provider", "purpose"),
    [
        (OTHER_WORKSPACE, "instagram", crypto.ACCESS_TOKEN_PURPOSE),
        (WORKSPACE, "demo", crypto.ACCESS_TOKEN_PURPOSE),
        (WORKSPACE, "instagram", crypto.REFRESH_TOKEN_PURPOSE),
    ],
)
def test_an_envelope_does_not_open_in_another_row(
    cipher_key: str, workspace_id: str, provider: str, purpose: str
) -> None:
    """Copying a ciphertext elsewhere must fail, not yield a working token."""

    del cipher_key
    envelope = crypto.encrypt_token(
        "bound-token",
        workspace_id=WORKSPACE,
        provider="instagram",
        purpose=crypto.ACCESS_TOKEN_PURPOSE,
    )
    with pytest.raises(crypto.TokenDecryptionError):
        crypto.decrypt_token(
            envelope, workspace_id=workspace_id, provider=provider, purpose=purpose
        )


def test_an_envelope_does_not_open_under_a_different_key(
    cipher_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    del cipher_key
    envelope = crypto.encrypt_token(
        "rotated-token",
        workspace_id=WORKSPACE,
        provider="instagram",
        purpose=crypto.ACCESS_TOKEN_PURPOSE,
    )
    monkeypatch.setattr(settings, "social_token_encryption_key", ROTATED_KEY)
    with pytest.raises(crypto.TokenDecryptionError):
        crypto.decrypt_token(
            envelope,
            workspace_id=WORKSPACE,
            provider="instagram",
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        )


def test_encryption_refuses_an_unknown_purpose_or_an_empty_scope(cipher_key: str) -> None:
    del cipher_key
    with pytest.raises(ValueError, match="Propósito"):
        crypto.encrypt_token(
            "token", workspace_id=WORKSPACE, provider="instagram", purpose="publish_token"
        )
    with pytest.raises(ValueError, match="workspace"):
        crypto.encrypt_token(
            "token", workspace_id="", provider="instagram", purpose=crypto.ACCESS_TOKEN_PURPOSE
        )
    with pytest.raises(ValueError, match="vacío"):
        crypto.encrypt_token(
            "", workspace_id=WORKSPACE, provider="instagram", purpose=crypto.ACCESS_TOKEN_PURPOSE
        )


@pytest.mark.parametrize("key", ["", "instagram-client-secret", "%%%"])
def test_without_a_usable_key_encryption_is_unavailable_rather_than_silent(
    monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setattr(settings, "social_token_encryption_key", key)
    assert crypto.encryption_available() is False
    with pytest.raises(crypto.TokenCipherUnavailable):
        crypto.encrypt_token(
            "token",
            workspace_id=WORKSPACE,
            provider="instagram",
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        )


def test_the_unavailable_error_is_a_503_that_names_no_secret() -> None:
    error = crypto.cipher_unavailable_error()
    assert error.status_code == 503
    assert error.code == "SOCIAL_CONNECTIONS_UNAVAILABLE"
    assert "SOCIAL_TOKEN_ENCRYPTION_KEY" not in error.message
    assert "key" not in error.message.casefold()


# --------------------------------------------------------------------------- #
# The single-use handshake
# --------------------------------------------------------------------------- #


def test_state_and_verifier_are_random_and_long_enough() -> None:
    states = {oauth_state.create_state() for _ in range(50)}
    assert len(states) == 50
    assert all(len(state) >= 32 for state in states)
    verifiers = {oauth_state.create_code_verifier() for _ in range(50)}
    assert len(verifiers) == 50
    # RFC 7636 requires 43-128 characters.
    assert all(43 <= len(verifier) <= 128 for verifier in verifiers)


def test_the_challenge_is_s256_and_does_not_carry_the_verifier() -> None:
    verifier = oauth_state.create_code_verifier()
    challenge = oauth_state.create_code_challenge(verifier)
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    assert challenge == expected
    assert verifier not in challenge
    assert "=" not in challenge


def test_the_raw_state_is_never_the_storage_key() -> None:
    state = oauth_state.create_state()
    fingerprint = oauth_state.state_fingerprint(state)
    assert fingerprint != state
    assert state not in fingerprint
    assert len(fingerprint) == 64


async def _remember(state: str, **overrides: object) -> None:
    payload: dict[str, object] = {
        "state": state,
        "provider": "demo",
        "workspace_id": "ws_test_001",
        "user_id": "usr_test_001",
        "code_verifier": oauth_state.create_code_verifier(),
        "redirect_uri": "http://api.test/api/v1/social/demo/callback",
        "return_path": "/settings",
        "scopes": ("demo_basic",),
    }
    payload.update(overrides)
    await oauth_state.remember(**payload)  # type: ignore[arg-type]


def _state_key(state: str) -> str:
    return f"{oauth_state._STATE_NAMESPACE}:{oauth_state.state_fingerprint(state)}"


def _used_key(state: str) -> str:
    return f"{oauth_state._USED_NAMESPACE}:{oauth_state.state_fingerprint(state)}"


class _BarrierBeforeLeaseStore:
    """Force two consumers to finish their payload read before leasing."""

    def __init__(self, inner: EphemeralStore) -> None:
        self.inner = inner
        self.payload_reads = 0
        self._both_payloads_read = asyncio.Event()
        self.lease_calls_before_both_reads = 0

    async def get(self, *, key: str) -> str | None:
        value = await self.inner.get(key=key)
        if key.startswith(f"{oauth_state._STATE_NAMESPACE}:"):
            self.payload_reads += 1
            if self.payload_reads == 2:
                self._both_payloads_read.set()
            await self._both_payloads_read.wait()
        return value

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        await self.inner.set(key=key, value=value, ttl_seconds=ttl_seconds)

    async def delete(self, *, key: str) -> None:
        await self.inner.delete(key=key)

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        if not self._both_payloads_read.is_set():
            self.lease_calls_before_both_reads += 1
        return await self.inner.acquire_lease(key=key, token=token, ttl_seconds=ttl_seconds)

    async def release_lease(self, *, key: str, token: str) -> None:
        await self.inner.release_lease(key=key, token=token)

    async def ensure_available(self) -> None:
        await self.inner.ensure_available()


class _SpyStore:
    """Read-only spy for unknown-state behavior."""

    def __init__(self) -> None:
        self.get_calls: list[str] = []
        self.set_calls: list[str] = []
        self.acquire_lease_calls: list[str] = []
        self.delete_calls: list[str] = []

    async def get(self, *, key: str) -> str | None:
        self.get_calls.append(key)
        return None

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        del value, ttl_seconds
        self.set_calls.append(key)

    async def delete(self, *, key: str) -> None:
        self.delete_calls.append(key)

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        del token, ttl_seconds
        self.acquire_lease_calls.append(key)
        return True

    async def release_lease(self, *, key: str, token: str) -> None:
        del key, token

    async def ensure_available(self) -> None:
        return None


@pytest.mark.asyncio
async def test_a_remembered_handshake_comes_back_whole(demo_provider: None) -> None:
    del demo_provider
    state = oauth_state.create_state()
    verifier = oauth_state.create_code_verifier()
    await _remember(state, code_verifier=verifier, return_path="/settings/connections")

    authorization, reason = await oauth_state.consume(state=state)
    assert reason is None
    assert authorization is not None
    assert authorization.provider == "demo"
    assert authorization.workspace_id == "ws_test_001"
    assert authorization.user_id == "usr_test_001"
    assert authorization.code_verifier == verifier
    assert authorization.redirect_uri == "http://api.test/api/v1/social/demo/callback"
    assert authorization.return_path == "/settings/connections"
    assert authorization.scopes == ("demo_basic",)


@pytest.mark.asyncio
async def test_an_unknown_state_is_invalid(demo_provider: None) -> None:
    del demo_provider
    authorization, reason = await oauth_state.consume(state=oauth_state.create_state())
    assert authorization is None
    assert reason == oauth_state.INVALID_STATE


@pytest.mark.asyncio
async def test_a_state_is_consumed_exactly_once(demo_provider: None) -> None:
    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)

    first, first_reason = await oauth_state.consume(state=state)
    assert first is not None
    assert first_reason is None

    replayed, replay_reason = await oauth_state.consume(state=state)
    assert replayed is None
    assert replay_reason == oauth_state.REPLAYED_STATE


@pytest.mark.asyncio
async def test_two_simultaneous_callbacks_produce_exactly_one_winner(demo_provider: None) -> None:
    """The loser of the lease is indistinguishable from a replay."""

    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)

    results = await asyncio.gather(
        oauth_state.consume(state=state), oauth_state.consume(state=state)
    )
    winners = [authorization for authorization, _ in results if authorization is not None]
    reasons = [reason for _, reason in results]
    assert len(winners) == 1
    assert oauth_state.REPLAYED_STATE in reasons


@pytest.mark.asyncio
async def test_two_concurrent_callbacks_really_contend_for_the_lease(
    demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)

    store = _BarrierBeforeLeaseStore(get_ephemeral_store())
    monkeypatch.setattr(oauth_state, "get_ephemeral_store", lambda: store)
    results = await asyncio.gather(
        oauth_state.consume(state=state), oauth_state.consume(state=state)
    )

    winners = [authorization for authorization, _ in results if authorization is not None]
    losers = [reason for authorization, reason in results if authorization is None]
    assert len(winners) == 1
    assert losers == [oauth_state.REPLAYED_STATE]
    assert store.payload_reads == 2
    assert store.lease_calls_before_both_reads == 0


@pytest.mark.asyncio
async def test_a_deleted_state_reports_replay_after_its_used_marker_is_written(
    demo_provider: None,
) -> None:
    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)
    store = get_ephemeral_store()

    authorization, reason = await oauth_state.consume(state=state)
    assert authorization is not None
    assert reason is None
    assert await store.get(key=_used_key(state)) is not None
    assert await store.get(key=_state_key(state)) is None

    replayed, replay_reason = await oauth_state.consume(state=state)
    assert replayed is None
    assert replay_reason == oauth_state.REPLAYED_STATE


@pytest.mark.asyncio
async def test_an_unknown_state_only_reads_storage(
    demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    store = _SpyStore()
    monkeypatch.setattr(oauth_state, "get_ephemeral_store", lambda: store)
    state = oauth_state.create_state()

    authorization, reason = await oauth_state.consume(state=state)

    assert authorization is None
    assert reason == oauth_state.INVALID_STATE
    assert store.get_calls == [_state_key(state), _used_key(state)]
    assert store.set_calls == []
    assert store.acquire_lease_calls == []
    assert store.delete_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("age", [timedelta(hours=2), timedelta(hours=-2)])
async def test_a_stale_or_future_dated_handshake_is_expired(
    demo_provider: None, age: timedelta
) -> None:
    """A clock that moved is not a reason to accept an old handshake."""

    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)
    store = get_ephemeral_store()
    raw = await store.get(key=_state_key(state))
    assert raw is not None
    payload = json.loads(raw)
    payload["issued_at"] = (datetime.now(UTC) - age).isoformat()
    await store.set(key=_state_key(state), value=json.dumps(payload), ttl_seconds=600)

    authorization, reason = await oauth_state.consume(state=state)
    assert authorization is None
    assert reason == oauth_state.EXPIRED_STATE


@pytest.mark.asyncio
async def test_a_corrupt_entry_is_invalid_and_still_burns_its_state(demo_provider: None) -> None:
    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)
    store = get_ephemeral_store()
    await store.set(key=_state_key(state), value="{not json", ttl_seconds=600)

    authorization, reason = await oauth_state.consume(state=state)
    assert authorization is None
    assert reason == oauth_state.INVALID_STATE

    # A broken write must not become a replay oracle: the state is spent either
    # way, so a second attempt is reported as a replay rather than retried.
    _, second_reason = await oauth_state.consume(state=state)
    assert second_reason in {oauth_state.INVALID_STATE, oauth_state.REPLAYED_STATE}


class _NoLeaseStore:
    """A store that can read but cannot promise single use."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.deleted: list[str] = []

    async def get(self, *, key: str) -> str | None:
        del key
        return self.payload

    async def set(self, *, key: str, value: str, ttl_seconds: int | None = None) -> None:
        del key, value, ttl_seconds

    async def delete(self, *, key: str) -> None:
        self.deleted.append(key)

    async def acquire_lease(self, *, key: str, token: str, ttl_seconds: int) -> bool | None:
        del key, token, ttl_seconds
        return None

    async def release_lease(self, *, key: str, token: str) -> None:
        del key, token

    async def ensure_available(self) -> None:
        return None


@pytest.mark.asyncio
async def test_without_single_use_storage_the_handshake_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No lease means no guarantee, and no guarantee means no connection."""

    store = _NoLeaseStore(
        json.dumps(
            {
                "provider": "demo",
                "workspace_id": "ws_test_001",
                "user_id": "usr_test_001",
                "code_verifier": "verifier",
                "redirect_uri": "http://api.test/api/v1/social/demo/callback",
                "return_path": "/settings",
                "scopes": ["demo_basic"],
                "issued_at": datetime.now(UTC).isoformat(),
            }
        )
    )
    monkeypatch.setattr(oauth_state, "get_ephemeral_store", lambda: store)
    authorization, reason = await oauth_state.consume(state=oauth_state.create_state())
    assert authorization is None
    assert reason == oauth_state.STORE_UNAVAILABLE
    # The payload was never trusted, so nothing was consumed either.
    assert store.deleted == []


def test_the_state_cookie_only_accepts_its_own_signature() -> None:
    state = oauth_state.create_state()
    response = Response()
    set_social_oauth_cookie(response, state=state)
    signed = response.headers["set-cookie"].split("=", 1)[1].split(";", 1)[0]

    assert read_social_oauth_cookie(signed) == state
    assert read_social_oauth_cookie(state) is None
    assert read_social_oauth_cookie(f"{state}.deadbeef") is None
    assert read_social_oauth_cookie(signed[:-1]) is None
    assert read_social_oauth_cookie(None) is None
    assert read_social_oauth_cookie("") is None
    # A different state with a stolen signature does not authenticate either.
    other = oauth_state.create_state()
    assert read_social_oauth_cookie(f"{other}.{signed.rpartition('.')[2]}") is None


# --------------------------------------------------------------------------- #
# Redirect safety
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "candidate",
    [
        None,
        "",
        "   ",
        "//evil.example.com",
        "https://evil.example.com/settings",
        "http://evil.example.com",
        "/settings/../../evil",
        "\\evil.example.com",
        "/settings?next=https://evil.example.com",
        "/settings#fragment",
        "settings",
        "/settings\n/evil",
        "/" + "a" * 200,
    ],
)
def test_only_a_plain_internal_path_survives_the_redirect_guard(candidate: str | None) -> None:
    assert service.safe_return_path(candidate) == service.DEFAULT_RETURN_PATH


@pytest.mark.parametrize(
    "candidate",
    ["/settings", "/settings/connections", "/a_b-c.d", "/", "/dashboard/projects/1"],
)
def test_internal_paths_are_preserved(candidate: str) -> None:
    assert service.safe_return_path(candidate) == candidate


@pytest.mark.parametrize(
    "return_path",
    ["https://evil.example.com", "//evil.example.com", "/settings"],
)
def test_the_callback_redirect_cannot_leave_the_application(
    monkeypatch: pytest.MonkeyPatch, return_path: str
) -> None:
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")
    target = service.callback_redirect(
        return_path=return_path,
        outcome=service.OUTCOME_ERROR,
        provider_name="demo",
        reason=service.REASON_INVALID_REQUEST,
    )
    assert target.startswith("http://frontend.test/")
    assert "evil.example.com" not in target


def test_a_failed_callback_reveals_only_a_neutral_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "frontend_url", "http://frontend.test")
    target = service.callback_redirect(
        return_path="/settings",
        outcome=service.OUTCOME_ERROR,
        provider_name="instagram",
        reason=service.REASON_PROVIDER_ERROR,
    )
    assert target == (
        "http://frontend.test/settings?social=error&provider=instagram&reason=provider_error"
    )


# --------------------------------------------------------------------------- #
# The provider factory
# --------------------------------------------------------------------------- #


def test_an_unknown_network_does_not_exist(demo_provider: None) -> None:
    del demo_provider
    assert providers.descriptor_for("myspace") is None
    assert providers.build_provider("myspace") is None
    assert providers.descriptor_for("../instagram") is None
    assert providers.build_provider("") is None


def test_the_demo_provider_is_invisible_when_it_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "social_connections_enabled", True)
    monkeypatch.setattr(settings, "social_demo_provider_enabled", False)
    names = [descriptor.name for descriptor in providers.provider_catalog()]
    assert "demo" not in names
    assert providers.descriptor_for("demo") is None
    assert providers.build_provider("demo") is None


def test_the_demo_provider_is_available_only_once_configured(demo_provider: None) -> None:
    del demo_provider
    descriptor = providers.descriptor_for("demo")
    assert descriptor is not None
    assert descriptor.status == providers.PROVIDER_AVAILABLE
    assert descriptor.reason_code is None
    assert providers.build_provider("demo") is not None


def test_an_unconfigured_network_is_reported_as_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "social_connections_enabled", True)
    monkeypatch.setattr(settings, "instagram_connections_enabled", True)
    monkeypatch.setattr(settings, "instagram_client_id", "")
    monkeypatch.setattr(settings, "instagram_client_secret", "")
    descriptor = providers.descriptor_for("instagram")
    assert descriptor is not None
    assert descriptor.status == providers.PROVIDER_UNCONFIGURED
    assert descriptor.reason_code == "not_configured"
    # No silent fallback to another network.
    assert providers.build_provider("instagram") is None


@pytest.mark.parametrize(
    ("name", "reason"),
    [("tiktok", "requires_platform_approval"), ("x", "requires_paid_plan")],
)
def test_an_acknowledged_but_unimplemented_network_is_honestly_disabled(
    name: str, reason: str
) -> None:
    descriptor = providers.descriptor_for(name)
    assert descriptor is not None
    assert descriptor.status == providers.PROVIDER_DISABLED
    assert descriptor.reason_code == reason
    assert descriptor.scopes == ()
    assert providers.build_provider(name) is None


def test_the_catalog_order_is_stable(demo_provider: None) -> None:
    del demo_provider
    names = tuple(descriptor.name for descriptor in providers.provider_catalog())
    assert names == providers.PROVIDER_ORDER


def test_no_provider_asks_for_permission_to_publish() -> None:
    for provider in (providers.InstagramSocialProvider(), providers.DemoSocialProvider()):
        joined = " ".join(provider.scopes).casefold()
        for forbidden in ("publish", "write", "manage", "post", "upload"):
            assert forbidden not in joined
    assert providers.InstagramSocialProvider().scopes == ("instagram_business_basic",)


def test_the_redirect_uri_is_configuration_and_stays_under_our_own_origin(
    demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    monkeypatch.setattr(
        settings, "instagram_redirect_uri", "http://api.test/api/v1/social/instagram/callback"
    )
    assert providers.redirect_uri_for("instagram") == (
        "http://api.test/api/v1/social/instagram/callback"
    )
    assert providers.redirect_uri_for("demo").startswith("http://api.test/")


def test_the_instagram_authorization_url_carries_no_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "instagram_client_id", "ig-client-id")
    monkeypatch.setattr(settings, "instagram_client_secret", "ig-client-secret-do-not-echo")
    url = providers.InstagramSocialProvider().build_authorization_url(
        state="state-value",
        code_challenge="challenge-value",
        redirect_uri="http://api.test/api/v1/social/instagram/callback",
    )
    assert "ig-client-secret-do-not-echo" not in url
    # PKCE is not claimed where it is not supported.
    assert "code_challenge" not in url
    assert "response_type=code" in url
    assert "instagram_business_basic" in url
    assert "publish" not in url


# --------------------------------------------------------------------------- #
# Error sanitization
# --------------------------------------------------------------------------- #

#: A provider error body of the kind that must never reach a caller: it quotes a
#: token, an internal id and a support URL.
LEAKY_BODY = {
    "error": {
        "message": "Invalid OAuth access token IGQVJYleaked-token-value for user 17841400000000000",
        "type": "OAuthException",
        "code": 190,
        "fbtrace_id": "AbCdEfGhIjK",
    }
}


def _mock_instagram(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(providers, "_client", factory)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, providers.ERROR_INVALID_GRANT),
        (401, providers.ERROR_TOKEN_REVOKED),
        (403, providers.ERROR_TOKEN_REVOKED),
        (404, providers.ERROR_PROVIDER_ERROR),
        (429, providers.ERROR_PROVIDER_UNAVAILABLE),
        (500, providers.ERROR_PROVIDER_UNAVAILABLE),
        (503, providers.ERROR_PROVIDER_UNAVAILABLE),
    ],
)
async def test_a_provider_failure_becomes_a_code_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, status_code: int, expected: str
) -> None:
    _mock_instagram(
        monkeypatch, lambda request: httpx.Response(status_code, json=LEAKY_BODY)
    )
    with pytest.raises(providers.SocialProviderError) as exc_info:
        await providers.InstagramSocialProvider().exchange_authorization_code(
            code="code", code_verifier="", redirect_uri="http://api.test/callback"
        )
    assert exc_info.value.code == expected
    rendered = repr(exc_info.value) + str(exc_info.value)
    assert "leaked-token-value" not in rendered
    assert "fbtrace_id" not in rendered
    assert "17841400000000000" not in rendered


@pytest.mark.asyncio
async def test_a_transport_failure_is_unavailable_not_an_error_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure for api.instagram.com", request=request)

    _mock_instagram(monkeypatch, explode)
    with pytest.raises(providers.SocialProviderError) as exc_info:
        await providers.InstagramSocialProvider().resolve_owned_accounts(access_token="token")
    assert exc_info.value.code == providers.ERROR_PROVIDER_UNAVAILABLE


@pytest.mark.asyncio
async def test_a_non_json_or_non_object_answer_is_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_instagram(monkeypatch, lambda request: httpx.Response(200, text="<html>maintenance"))
    with pytest.raises(providers.SocialProviderError) as exc_info:
        await providers.InstagramSocialProvider().resolve_owned_accounts(access_token="token")
    assert exc_info.value.code == providers.ERROR_PROVIDER_ERROR

    _mock_instagram(monkeypatch, lambda request: httpx.Response(200, json=["not", "an", "object"]))
    with pytest.raises(providers.SocialProviderError) as exc_info:
        await providers.InstagramSocialProvider().resolve_owned_accounts(access_token="token")
    assert exc_info.value.code == providers.ERROR_PROVIDER_ERROR


@pytest.mark.asyncio
async def test_an_account_without_an_id_is_not_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_instagram(monkeypatch, lambda request: httpx.Response(200, json={"username": "who"}))
    with pytest.raises(providers.SocialProviderError) as exc_info:
        await providers.InstagramSocialProvider().resolve_owned_accounts(access_token="token")
    assert exc_info.value.code == providers.ERROR_NO_ELIGIBLE_ACCOUNT


@pytest.mark.asyncio
async def test_an_unfamiliar_account_type_is_recorded_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_instagram(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"id": "1789", "username": "tienda", "account_type": "SOMETHING_NEW"}
        ),
    )
    accounts = await providers.InstagramSocialProvider().resolve_owned_accounts(
        access_token="token"
    )
    assert accounts[0].account_type == "unknown"
    assert accounts[0].provider_account_id == "1789"
    assert accounts[0].display_name == "tienda"


@pytest.mark.asyncio
async def test_a_revoked_token_makes_a_check_say_revoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_instagram(monkeypatch, lambda request: httpx.Response(401, json=LEAKY_BODY))
    result = await providers.InstagramSocialProvider().validate_connection(
        access_token="token", provider_account_id="1789"
    )
    assert result.status == "revoked"
    assert result.error_code == providers.ERROR_TOKEN_REVOKED


@pytest.mark.asyncio
async def test_a_token_that_speaks_for_another_account_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A working token pointing elsewhere must not silently repoint the row."""

    _mock_instagram(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"id": "9999", "username": "otra", "account_type": "BUSINESS"}
        ),
    )
    result = await providers.InstagramSocialProvider().validate_connection(
        access_token="token", provider_account_id="1789"
    )
    assert result.status == "revoked"
    assert result.error_code == providers.ERROR_TOKEN_REVOKED


@pytest.mark.asyncio
async def test_an_unreachable_network_degrades_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_instagram(monkeypatch, lambda request: httpx.Response(503, text="upstream down"))
    result = await providers.InstagramSocialProvider().validate_connection(
        access_token="token", provider_account_id="1789"
    )
    assert result.status == "degraded"
    assert result.error_code == providers.ERROR_PROVIDER_UNAVAILABLE


# --------------------------------------------------------------------------- #
# Scope discipline
# --------------------------------------------------------------------------- #


def test_scopes_the_user_never_consented_to_are_refused() -> None:
    with pytest.raises(providers.SocialProviderError) as exc_info:
        service._reject_unexpected_scopes(
            granted=("instagram_business_basic", "instagram_business_content_publish"),
            requested=("instagram_business_basic",),
        )
    assert exc_info.value.code == providers.ERROR_UNEXPECTED_SCOPE


def test_a_missing_scope_is_refused_too() -> None:
    with pytest.raises(providers.SocialProviderError):
        service._reject_unexpected_scopes(
            granted=("something_else",), requested=("instagram_business_basic",)
        )


def test_silence_about_scopes_is_not_evidence_of_extra_authority() -> None:
    """Several providers report nothing. Absence is accepted; a claim is checked."""

    service._reject_unexpected_scopes(granted=(), requested=("instagram_business_basic",))
    service._reject_unexpected_scopes(granted=("",), requested=("instagram_business_basic",))
    service._reject_unexpected_scopes(
        granted=("instagram_business_basic",), requested=("instagram_business_basic",)
    )


# --------------------------------------------------------------------------- #
# Service and route coverage
# --------------------------------------------------------------------------- #


class _StubSocialProvider:
    """An in-process provider seam for persistence and callback tests."""

    name = "demo"
    supports_pkce = True
    scopes = ("demo_basic",)

    def __init__(
        self,
        *,
        accounts: tuple[providers.OwnedAccount, ...] | None = None,
        exchange_error: providers.SocialProviderError | None = None,
        validation_result: providers.ConnectionCheck | None = None,
        revoke_result: bool = True,
        revoke_error: providers.SocialProviderError | None = None,
    ) -> None:
        self.accounts = accounts or (
            providers.OwnedAccount(
                provider_account_id="stub-account",
                display_name="cuenta.stub",
                account_type="business",
            ),
        )
        self.exchange_error = exchange_error
        self.validation_result = validation_result or providers.ConnectionCheck(
            status="connected"
        )
        self.revoke_result = revoke_result
        self.revoke_error = revoke_error
        self.revoke_calls = 0

    def build_authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str:
        del state, code_challenge, redirect_uri
        return "http://provider.test/authorize"

    async def exchange_authorization_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> providers.ProviderToken:
        del code_verifier, redirect_uri
        if self.exchange_error is not None:
            raise self.exchange_error
        return providers.ProviderToken(
            access_token=f"stub-access-{code}",
            refresh_token=f"stub-refresh-{code}",
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
        return self.validation_result

    async def revoke_connection(self, *, access_token: str, provider_account_id: str) -> bool:
        del access_token, provider_account_id
        self.revoke_calls += 1
        if self.revoke_error is not None:
            raise self.revoke_error
        return self.revoke_result


def _callback_params(target: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(target).query)


def _assert_callback_result(target: str, *, outcome: str, reason: str | None = None) -> None:
    params = _callback_params(target)
    assert params["social"] == [outcome]
    if reason is not None:
        assert params["reason"] == [reason]


def _token(
    access_token: str,
    *,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> providers.ProviderToken:
    return providers.ProviderToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        granted_scopes=("demo_basic",),
    )


async def _save_connected(
    db,
    *,
    workspace_id: str = "ws_test_001",
    provider_name: str = "demo",
    account_id: str = "demo-account",
    display_name: str = "cuenta.demo",
    account_type: str = "business",
    access_token: str = "demo-access-token",
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> SocialConnection:
    connection = await service._upsert_connection(
        db,
        workspace_id=workspace_id,
        provider_name=provider_name,
        account=providers.OwnedAccount(
            provider_account_id=account_id,
            display_name=display_name,
            account_type=account_type,
        ),
        token=_token(
            access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        ),
    )
    assert connection is not None
    await db.commit()
    return connection


@pytest.mark.asyncio
async def test_demo_callback_route_persists_one_encrypted_connection(
    client, db_session, demo_provider: None
) -> None:
    del demo_provider
    start = await client.post(
        "/api/v1/social/demo/authorize", json={"return_path": "/settings/connections"}
    )
    assert start.status_code == 200
    authorization_query = parse_qs(urlparse(start.json()["authorization_url"]).query)
    state = authorization_query["state"][0]
    plaintext = f"demo-access-{state[:16]}"

    callback = await client.get(
        "/api/v1/social/demo/callback",
        params={"code": authorization_query["code"][0], "state": state},
        follow_redirects=False,
    )

    assert callback.status_code == 303
    _assert_callback_result(callback.headers["location"], outcome=service.OUTCOME_CONNECTED)
    result = await db_session.execute(select(SocialConnection))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].status == "connected"
    assert rows[0].encrypted_access_token is not None
    assert rows[0].encrypted_access_token != plaintext
    assert plaintext not in rows[0].encrypted_access_token


@pytest.mark.asyncio
async def test_callback_invalid_state_provider_and_cookie_are_neutral(
    db_session, demo_provider: None
) -> None:
    del demo_provider
    invalid = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="demo-code-invalid",
        state="state-not-remembered",
        cookie_state="state-not-remembered",
        provider_error=None,
    )
    _assert_callback_result(
        invalid,
        outcome=service.OUTCOME_ERROR,
        reason=service.REASON_INVALID_REQUEST,
    )

    wrong_provider_state = oauth_state.create_state()
    await _remember(wrong_provider_state)
    wrong_provider = await service.complete_callback(
        db_session,
        provider_name="instagram",
        code="code",
        state=wrong_provider_state,
        cookie_state=wrong_provider_state,
        provider_error=None,
    )
    _assert_callback_result(
        wrong_provider,
        outcome=service.OUTCOME_ERROR,
        reason=service.REASON_INVALID_REQUEST,
    )

    missing_cookie_state = oauth_state.create_state()
    await _remember(missing_cookie_state)
    missing_cookie = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="demo-code-missing-cookie",
        state=missing_cookie_state,
        cookie_state=None,
        provider_error=None,
    )
    _assert_callback_result(
        missing_cookie,
        outcome=service.OUTCOME_ERROR,
        reason=service.REASON_INVALID_REQUEST,
    )


@pytest.mark.asyncio
async def test_provider_denial_is_redirected_as_denied(db_session, demo_provider: None) -> None:
    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)

    target = await service.complete_callback(
        db_session,
        provider_name="demo",
        code=None,
        state=state,
        cookie_state=state,
        provider_error="access_denied",
    )

    _assert_callback_result(target, outcome=service.OUTCOME_ERROR, reason=service.REASON_DENIED)
    result = await db_session.execute(select(SocialConnection))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_code",
    [
        providers.ERROR_INVALID_GRANT,
        providers.ERROR_TOKEN_REVOKED,
        providers.ERROR_PROVIDER_ERROR,
        providers.ERROR_PROVIDER_UNAVAILABLE,
    ],
)
async def test_provider_error_types_are_neutral_callback_errors(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch, error_code: str
) -> None:
    del demo_provider
    stub = _StubSocialProvider(exchange_error=providers.SocialProviderError(error_code))
    monkeypatch.setattr(providers, "build_provider", lambda name: stub if name == "demo" else None)
    state = oauth_state.create_state()
    await _remember(state)

    target = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="provider-error-code",
        state=state,
        cookie_state=state,
        provider_error=None,
    )

    _assert_callback_result(
        target,
        outcome=service.OUTCOME_ERROR,
        reason=service.REASON_PROVIDER_ERROR,
    )


@pytest.mark.asyncio
async def test_missing_provider_maps_to_the_existing_unavailable_reason(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    monkeypatch.setattr(providers, "build_provider", lambda name: None)
    state = oauth_state.create_state()
    await _remember(state)

    target = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="provider-unavailable-code",
        state=state,
        cookie_state=state,
        provider_error=None,
    )

    _assert_callback_result(target, outcome=service.OUTCOME_ERROR, reason=service.REASON_UNAVAILABLE)


@pytest.mark.asyncio
async def test_second_authorization_updates_one_existing_account_row(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    stub = _StubSocialProvider(
        accounts=(
            providers.OwnedAccount(
                provider_account_id="same-account",
                display_name="primera.cuenta",
                account_type="business",
            ),
        )
    )
    monkeypatch.setattr(providers, "build_provider", lambda name: stub if name == "demo" else None)

    first_state = oauth_state.create_state()
    await _remember(first_state)
    first = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="first-callback",
        state=first_state,
        cookie_state=first_state,
        provider_error=None,
    )
    _assert_callback_result(first, outcome=service.OUTCOME_CONNECTED)

    stub.accounts = (
        providers.OwnedAccount(
            provider_account_id="same-account",
            display_name="segunda.cuenta",
            account_type="creator",
        ),
    )
    second_state = oauth_state.create_state()
    await _remember(second_state)
    second = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="second-callback",
        state=second_state,
        cookie_state=second_state,
        provider_error=None,
    )
    _assert_callback_result(second, outcome=service.OUTCOME_CONNECTED)

    result = await db_session.execute(select(SocialConnection))
    rows = list(result.scalars().all())
    assert len(rows) == 1
    assert rows[0].display_name == "segunda.cuenta"
    assert rows[0].account_type == "creator"
    assert crypto.decrypt_token(
        rows[0].encrypted_access_token or "",
        workspace_id="ws_test_001",
        provider="demo",
        purpose=crypto.ACCESS_TOKEN_PURPOSE,
    ) == "stub-access-second-callback"


@pytest.mark.asyncio
async def test_integrity_error_race_reloads_and_updates_the_winning_row(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    now = datetime.now(UTC)
    first_access = "race-first-access"
    competitor = SocialConnection(
        workspace_id="ws_test_001",
        provider="demo",
        provider_account_id="race-account",
        display_name="primera.cuenta",
        account_type="business",
        status="connected",
        encrypted_access_token=crypto.encrypt_token(
            first_access,
            workspace_id="ws_test_001",
            provider="demo",
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        ),
        encrypted_refresh_token=None,
        last_checked_at=now,
        connected_at=now,
    )
    db_session.add(competitor)
    await db_session.commit()

    original_scalar = db_session.scalar
    fast_path = True

    async def hide_competitor_on_fast_path(statement, *args, **kwargs):
        nonlocal fast_path
        if fast_path:
            fast_path = False
            return None
        return await original_scalar(statement, *args, **kwargs)

    monkeypatch.setattr(db_session, "scalar", hide_competitor_on_fast_path)
    result = await service._upsert_connection(
        db_session,
        workspace_id="ws_test_001",
        provider_name="demo",
        account=providers.OwnedAccount(
            provider_account_id="race-account",
            display_name="segunda.cuenta",
            account_type="creator",
        ),
        token=_token("race-second-access", refresh_token="race-second-refresh"),
    )
    assert result is not None
    await db_session.commit()

    rows_result = await db_session.execute(select(SocialConnection))
    rows = list(rows_result.scalars().all())
    assert len(rows) == 1
    assert rows[0].display_name == "segunda.cuenta"
    assert rows[0].account_type == "creator"
    assert crypto.decrypt_token(
        rows[0].encrypted_access_token or "",
        workspace_id="ws_test_001",
        provider="demo",
        purpose=crypto.ACCESS_TOKEN_PURPOSE,
    ) == "race-second-access"
    assert crypto.decrypt_token(
        rows[0].encrypted_refresh_token or "",
        workspace_id="ws_test_001",
        provider="demo",
        purpose=crypto.REFRESH_TOKEN_PURPOSE,
    ) == "race-second-refresh"


@pytest.mark.asyncio
async def test_multi_account_provider_is_rejected_without_writes(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    stub = _StubSocialProvider(
        accounts=(
            providers.OwnedAccount("account-one", "primera", "business"),
            providers.OwnedAccount("account-two", "segunda", "creator"),
        )
    )
    monkeypatch.setattr(providers, "build_provider", lambda name: stub if name == "demo" else None)
    state = oauth_state.create_state()
    await _remember(state)

    target = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="multi-account-code",
        state=state,
        cookie_state=state,
        provider_error=None,
    )

    _assert_callback_result(
        target,
        outcome=service.OUTCOME_ERROR,
        reason=service.REASON_PROVIDER_ERROR,
    )
    result = await db_session.execute(select(SocialConnection))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_list_connections_returns_catalog_and_only_this_workspace(
    client, db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    monkeypatch.setattr(settings, "instagram_connections_enabled", True)
    monkeypatch.setattr(settings, "instagram_client_id", "")
    monkeypatch.setattr(settings, "instagram_client_secret", "")
    db_session.add(Workspace(id="ws_other_001", name="Other workspace"))
    await db_session.commit()

    own = await _save_connected(
        db_session,
        account_id="shared-account",
        display_name="cuenta propia",
        access_token="own-access-token",
    )
    foreign = await _save_connected(
        db_session,
        workspace_id="ws_other_001",
        account_id="shared-account",
        display_name="cuenta extranjera",
        access_token="foreign-access-token",
    )

    response = await client.get("/api/v1/social/connections")
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    providers_by_name = {item["name"]: item for item in payload["providers"]}
    assert set(providers_by_name) == {"instagram", "tiktok", "x", "demo"}
    assert providers_by_name["demo"]["status"] == providers.PROVIDER_AVAILABLE
    assert providers_by_name["instagram"]["status"] == providers.PROVIDER_UNCONFIGURED
    assert providers_by_name["tiktok"]["status"] == providers.PROVIDER_DISABLED
    assert providers_by_name["x"]["status"] == providers.PROVIDER_DISABLED
    assert [item["id"] for item in payload["connections"]] == [own.id]
    assert foreign.id not in {item["id"] for item in payload["connections"]}
    assert all(item["display_name"] != "cuenta extranjera" for item in payload["connections"])


@pytest.mark.asyncio
async def test_check_connection_missing_provider_is_degraded(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    connection = await _save_connected(
        db_session,
        provider_name="instagram",
        account_id="instagram-account",
        access_token="instagram-access-token",
    )
    monkeypatch.setattr(providers, "build_provider", lambda name: None)

    checked = await service.check_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )

    assert checked.status == "degraded"
    assert checked.last_error_code == providers.ERROR_PROVIDER_UNAVAILABLE


@pytest.mark.asyncio
async def test_check_connection_reports_an_undecryptable_token(
    db_session, demo_provider: None
) -> None:
    del demo_provider
    connection = SocialConnection(
        workspace_id="ws_test_001",
        provider="demo",
        provider_account_id="unreadable-account",
        display_name="cuenta ilegible",
        account_type="business",
        status="connected",
        encrypted_access_token="not-an-envelope",
    )
    db_session.add(connection)
    await db_session.commit()

    checked = await service.check_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )

    assert checked.status == "error"
    assert checked.last_error_code == providers.ERROR_TOKEN_UNREADABLE


@pytest.mark.asyncio
async def test_check_connection_clears_stale_expiry_when_provider_accepts_token(
    db_session, demo_provider: None
) -> None:
    del demo_provider
    connection = await _save_connected(
        db_session,
        account_id="stale-account",
        access_token="demo-access-valid",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    checked = await service.check_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )

    assert checked.status == "connected"
    assert checked.token_expires_at is None


@pytest.mark.asyncio
async def test_foreign_connection_id_is_not_found_by_service_or_route(
    client, db_session, demo_provider: None
) -> None:
    del demo_provider
    db_session.add(Workspace(id="ws_other_002", name="Foreign workspace"))
    await db_session.commit()
    foreign = SocialConnection(
        workspace_id="ws_other_002",
        provider="demo",
        provider_account_id="foreign-check-account",
        display_name="cuenta ajena",
        account_type="business",
        status="disconnected",
        disconnected_at=datetime.now(UTC),
    )
    db_session.add(foreign)
    await db_session.commit()

    with pytest.raises(NotFoundError):
        await service.check_connection(
            db_session, workspace_id="ws_test_001", connection_id=foreign.id
        )
    response = await client.post(f"/api/v1/social/connections/{foreign.id}/check")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_disconnect_destroys_credentials_even_when_revoke_is_unconfirmed(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    stub = _StubSocialProvider(revoke_result=False)
    monkeypatch.setattr(providers, "build_provider", lambda name: stub if name == "demo" else None)
    connection = await _save_connected(
        db_session,
        access_token="disconnect-access-token",
        refresh_token="disconnect-refresh-token",
    )

    first = await service.disconnect_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )
    first_disconnected_at = first.disconnected_at
    first_checked_at = first.last_checked_at
    assert first.status == "disconnected"
    assert first.encrypted_access_token is None
    assert first.encrypted_refresh_token is None
    assert first.disconnected_at is not None
    assert first.last_error_code == providers.ERROR_REVOKE_UNCONFIRMED

    second = await service.disconnect_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )
    assert second.status == "disconnected"
    assert second.encrypted_access_token is None
    assert second.encrypted_refresh_token is None
    assert second.disconnected_at == first_disconnected_at
    assert second.last_checked_at == first_checked_at
    assert second.last_error_code == providers.ERROR_REVOKE_UNCONFIRMED
    assert stub.revoke_calls == 1


@pytest.mark.asyncio
async def test_callback_database_failure_is_neutral_and_rolls_back(
    db_session, demo_provider: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del demo_provider
    state = oauth_state.create_state()
    await _remember(state)

    async def fail_persistence(*args, **kwargs):
        del args, kwargs
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(service, "_upsert_connection", fail_persistence)
    target = await service.complete_callback(
        db_session,
        provider_name="demo",
        code="database-failure-code",
        state=state,
        cookie_state=state,
        provider_error=None,
    )

    _assert_callback_result(
        target,
        outcome=service.OUTCOME_ERROR,
        reason=service.REASON_PROVIDER_ERROR,
    )
    result = await db_session.execute(select(SocialConnection))
    assert list(result.scalars().all()) == []


@pytest.mark.asyncio
async def test_social_serialization_exposes_only_safe_fields(
    db_session, demo_provider: None
) -> None:
    del demo_provider
    access_token = "plain-access-token-never-serialize"
    refresh_token = "plain-refresh-token-never-serialize"
    connection = await _save_connected(
        db_session,
        account_id="safe-account",
        access_token=access_token,
        refresh_token=refresh_token,
    )
    connection.last_error_code = providers.ERROR_PROVIDER_ERROR
    connection.status = "error"
    await db_session.commit()
    envelope = connection.encrypted_access_token
    refresh_envelope = connection.encrypted_refresh_token

    serialized = service.serialize_connection(connection)
    listed = await service.list_connections(db_session, workspace_id="ws_test_001")
    checked = await service.check_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )
    checked_payload = service.serialize_connection(checked)
    disconnected = await service.disconnect_connection(
        db_session, workspace_id="ws_test_001", connection_id=connection.id
    )
    disconnected_payload = service.serialize_connection(disconnected)

    state = oauth_state.create_state()
    await _remember(state, return_path="/settings/connections")
    redirect = await service.complete_callback(
        db_session,
        provider_name="demo",
        code=None,
        state=state,
        cookie_state=state,
        provider_error="provider-error-body",
    )
    payloads = [
        serialized,
        listed,
        {"connection": checked_payload},
        {"connection": disconnected_payload},
    ]
    rendered = json.dumps(payloads, default=str) + redirect
    expected_keys = {
        "id",
        "provider",
        "display_name",
        "account_type",
        "status",
        "connected_at",
        "last_checked_at",
        "safe_error",
    }
    assert set(serialized) == expected_keys
    assert all(set(item["connection"]) == expected_keys for item in payloads[2:])
    for secret in (
        access_token,
        envelope,
        refresh_token,
        refresh_envelope,
        "leaked-token-value",
        "fbtrace_id",
        "17841400000000000",
        providers.redirect_uri_for("demo"),
    ):
        assert secret is not None
        assert secret not in rendered
