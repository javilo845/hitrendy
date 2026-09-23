"""The short-lived half of the OAuth handshake.

Everything the callback needs to trust itself lives here, and none of it lives
in the durable table: the PKCE verifier, the exact redirect URI, the provider
we meant to talk to, the workspace and the user who started it, and the
internal page to return to. A callback that cannot produce a matching entry is
a callback we did not start.

The entry lives in the ephemeral store rather than in process memory, because
the browser that leaves for the provider is under no obligation to come back to
the instance it left from. In staging and production the store is Redis, so any
instance can finish any handshake -- and none of them can finish one twice.

Single use is enforced with a lease, not with a read-then-delete: overlapping
callbacks can both see the entry, and exactly one of them wins ``SET NX`` on the
companion key. The loser is indistinguishable from a replay, whether it loses
the lease while the payload still exists or probes the used marker after the
winner has deleted the payload.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.ephemeral_store import get_ephemeral_store

#: 256 bits of entropy in the value the provider echoes back.
STATE_BYTES = 32
#: RFC 7636 allows 43-128 characters; 64 random bytes lands comfortably inside.
VERIFIER_BYTES = 64

_STATE_NAMESPACE = "social:oauth:state"
_USED_NAMESPACE = "social:oauth:used"

#: Rejection reasons. They are internal: the callback maps every one of them to
#: the same neutral outcome in the URL it redirects to.
INVALID_STATE = "invalid_state"
EXPIRED_STATE = "expired_state"
REPLAYED_STATE = "replayed_state"
STORE_UNAVAILABLE = "store_unavailable"


@dataclass(frozen=True)
class PendingAuthorization:
    """What the server remembered when it sent the user to the provider."""

    provider: str
    workspace_id: str
    user_id: str
    code_verifier: str
    redirect_uri: str
    return_path: str
    scopes: tuple[str, ...]
    issued_at: datetime


def create_state() -> str:
    return secrets.token_urlsafe(STATE_BYTES)


def create_code_verifier() -> str:
    return secrets.token_urlsafe(VERIFIER_BYTES)


def create_code_challenge(code_verifier: str) -> str:
    """S256, the only challenge method this codebase offers.

    ``plain`` is not implemented on purpose: it would let anyone who observes
    the authorization request complete the exchange.
    """

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def state_fingerprint(state: str) -> str:
    """The key derived from a state value.

    The raw state never becomes a key: keys leak into logs, slow-query traces
    and monitoring far more readily than values do.
    """

    return hashlib.sha256(state.encode("utf-8")).hexdigest()


async def remember(
    *,
    state: str,
    provider: str,
    workspace_id: str,
    user_id: str,
    code_verifier: str,
    redirect_uri: str,
    return_path: str,
    scopes: tuple[str, ...],
) -> None:
    """Store the pending handshake for as long as it may legitimately take."""

    payload = json.dumps(
        {
            "provider": provider,
            "workspace_id": workspace_id,
            "user_id": user_id,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "return_path": return_path,
            "scopes": list(scopes),
            "issued_at": datetime.now(UTC).isoformat(),
        },
        separators=(",", ":"),
    )
    await get_ephemeral_store().set(
        key=f"{_STATE_NAMESPACE}:{state_fingerprint(state)}",
        value=payload,
        ttl_seconds=settings.social_oauth_state_ttl_seconds,
    )


async def consume(*, state: str) -> tuple[PendingAuthorization | None, str | None]:
    """Claim a pending handshake exactly once.

    Returns ``(authorization, None)`` to the single caller that wins, and
    ``(None, reason)`` to every other one.
    """

    store = get_ephemeral_store()
    fingerprint = state_fingerprint(state)
    raw = await store.get(key=f"{_STATE_NAMESPACE}:{fingerprint}")
    if raw is None:
        used = await store.get(key=f"{_USED_NAMESPACE}:{fingerprint}")
        if used is not None:
            return None, REPLAYED_STATE
        return None, INVALID_STATE

    # The lease is taken before the payload is trusted: a malformed entry must
    # still burn its state, or a broken write would become a replay oracle.
    won = await store.acquire_lease(
        key=f"{_USED_NAMESPACE}:{fingerprint}",
        token=fingerprint,
        ttl_seconds=settings.social_oauth_state_ttl_seconds,
    )
    if won is None:
        # No distributed store means no single-use guarantee. Refusing is the
        # only honest answer; the configuration check makes this unreachable.
        return None, STORE_UNAVAILABLE
    if not won:
        return None, REPLAYED_STATE
    # acquire_lease must stay above delete: the used marker is the durable
    # evidence that turns a post-delete callback into REPLAYED_STATE. Swapping
    # these calls silently degrades replay reporting back to INVALID_STATE.
    await store.delete(key=f"{_STATE_NAMESPACE}:{fingerprint}")

    try:
        data = json.loads(raw)
        issued_at = datetime.fromisoformat(str(data["issued_at"]))
        authorization = PendingAuthorization(
            provider=str(data["provider"]),
            workspace_id=str(data["workspace_id"]),
            user_id=str(data["user_id"]),
            code_verifier=str(data["code_verifier"]),
            redirect_uri=str(data["redirect_uri"]),
            return_path=str(data["return_path"]),
            scopes=tuple(str(scope) for scope in data.get("scopes", ())),
            issued_at=issued_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, INVALID_STATE

    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - issued_at).total_seconds()
    if age < 0 or age > settings.social_oauth_state_ttl_seconds:
        # The store's own TTL usually gets here first. This check exists for the
        # cases where it does not: a clock change, a store that sweeps lazily,
        # or an operator who shortened the TTL after the entry was written.
        return None, EXPIRED_STATE
    return authorization, None
