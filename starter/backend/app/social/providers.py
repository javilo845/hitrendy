"""The seam between this application and a social network.

Everything network-specific stops here. The service above talks to
:class:`SocialConnectionProvider` and never to an endpoint, a field name or an
error body; the frontend below is told a provider's *name* and *status* and
nothing else, so adding or retiring a network is a server-side decision.

The catalog is deliberately short, and two of its entries are honest refusals:

* ``instagram`` -- Instagram Login for Business. Implemented.
* ``demo``      -- offline. Development and test only, never staging or
  production, because a fake connection presented as real is worse than no
  connection at all.
* ``tiktok``    -- listed as ``disabled``: the Content Posting and Display APIs
  require per-application approval this project does not hold.
* ``x``         -- listed as ``disabled``: the API tier this would need is paid.

Listing the last two costs nothing and prevents the worse outcome, which is a
user wondering whether we simply forgot. Neither has an implementation to fall
back to, and no request can ever select one.

No method in this module publishes anything. The only scopes requested are the
ones needed to learn *which account was connected*, and a scope is never
requested "for later".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from app.core.config import settings

#: Provider-facing statuses the UI may render for a network we know about.
PROVIDER_AVAILABLE = "available"
PROVIDER_UNCONFIGURED = "unconfigured"
PROVIDER_DISABLED = "disabled"

#: Account shapes we are willing to record. Anything a provider reports outside
#: this set becomes ``unknown`` rather than a free-text field fed by a remote
#: system.
ACCOUNT_TYPES = ("business", "creator", "personal", "unknown")

#: Normalized failure codes. The provider's own message never reaches a caller:
#: it is written by someone else, may quote the user's data back, and changes
#: without notice.
ERROR_INVALID_GRANT = "invalid_grant"
ERROR_TOKEN_EXPIRED = "token_expired"
ERROR_TOKEN_REVOKED = "token_revoked"
ERROR_INSUFFICIENT_SCOPE = "insufficient_scope"
#: The provider granted authority we never asked for. Treated as a failure, not
#: as a bonus: the consent screen described something narrower.
ERROR_UNEXPECTED_SCOPE = "unexpected_scope"
ERROR_NO_ELIGIBLE_ACCOUNT = "no_eligible_account"
ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
ERROR_PROVIDER_ERROR = "provider_error"
#: The stored envelope did not open. The credential is gone from our side even
#: if it still exists on the network's.
ERROR_TOKEN_UNREADABLE = "token_unreadable"
#: Disconnected locally, but the network never confirmed the revocation. The UI
#: uses this to tell the user to check the network's own app settings.
ERROR_REVOKE_UNCONFIRMED = "revoke_unconfirmed"


class SocialProviderError(Exception):
    """A provider refused, failed or answered with something unusable.

    ``code`` is one of the normalized constants above and is safe to store and
    to return. The original body is not carried at all, so it cannot leak by
    being logged later.
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class ProviderToken:
    """What an authorization code was exchanged for."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    granted_scopes: tuple[str, ...]


@dataclass(frozen=True)
class OwnedAccount:
    """One account the freshly exchanged token proves the user owns.

    Three fields, all public on the network itself. No email, no legal name, no
    audience numbers: none of them are needed to name a connection, and each
    one would be personal data we chose to copy for no reason.
    """

    provider_account_id: str
    display_name: str
    account_type: str


@dataclass(frozen=True)
class ConnectionCheck:
    """The result of asking a provider whether a stored token still works."""

    status: str
    error_code: str | None = None


@dataclass(frozen=True)
class ProviderDescriptor:
    """What the UI is allowed to know about a network."""

    name: str
    status: str
    reason_code: str | None
    supports_pkce: bool
    scopes: tuple[str, ...]


class SocialConnectionProvider(Protocol):
    """Connect an account. Nothing in this interface can post."""

    name: str
    supports_pkce: bool
    scopes: tuple[str, ...]

    def build_authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str: ...

    async def exchange_authorization_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> ProviderToken: ...

    async def resolve_owned_accounts(
        self, *, access_token: str
    ) -> tuple[OwnedAccount, ...]: ...

    async def validate_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> ConnectionCheck: ...

    async def revoke_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> bool: ...


def _normalize_account_type(value: object) -> str:
    candidate = str(value or "").strip().casefold()
    if candidate in {"business", "media_creator", "creator", "personal"}:
        return "creator" if candidate == "media_creator" else candidate
    return "unknown"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=settings.social_http_timeout_seconds)


class DemoSocialProvider:
    """An offline network. Exercises the whole flow without leaving the process.

    The authorization URL points straight back at our own callback, so the
    handshake -- state, single use, exchange, account resolution, storage --
    runs end to end in development and in tests without a single outbound
    request. It is refused outside development and test by configuration, and
    the connection it produces is labelled ``demo`` wherever it is shown.
    """

    name = "demo"
    supports_pkce = True
    scopes: tuple[str, ...] = ("demo_basic",)

    def build_authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str:
        del code_challenge
        # The verifier is still checked below; the URL only has to bring the
        # browser back the way a real provider would.
        return f"{redirect_uri}?code=demo-code-{state[:16]}&state={state}"

    async def exchange_authorization_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> ProviderToken:
        del redirect_uri
        if not code.startswith("demo-code-") or not code_verifier:
            raise SocialProviderError(ERROR_INVALID_GRANT)
        return ProviderToken(
            access_token=f"demo-access-{code[len('demo-code-'):]}",
            refresh_token=None,
            expires_at=datetime.now(UTC) + timedelta(days=60),
            granted_scopes=self.scopes,
        )

    async def resolve_owned_accounts(self, *, access_token: str) -> tuple[OwnedAccount, ...]:
        if not access_token.startswith("demo-access-"):
            raise SocialProviderError(ERROR_TOKEN_REVOKED)
        return (
            OwnedAccount(
                provider_account_id=f"demo-{access_token[len('demo-access-'):]}",
                display_name="cuenta.demo",
                account_type="business",
            ),
        )

    async def validate_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> ConnectionCheck:
        del provider_account_id
        if not access_token.startswith("demo-access-"):
            return ConnectionCheck(status="revoked", error_code=ERROR_TOKEN_REVOKED)
        return ConnectionCheck(status="connected")

    async def revoke_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> bool:
        del access_token, provider_account_id
        return True


class InstagramSocialProvider:
    """Instagram Login for Business.

    One scope, ``instagram_business_basic``, which is what the platform
    requires to tell us the id, username and account type of the professional
    account the user just authorized. The publishing scope exists and is not
    requested: this wave connects accounts, and a permission we do not need is
    a permission we cannot misuse.

    PKCE is not sent. Instagram's business login does not document support for
    it, and pretending otherwise would put an unverifiable parameter on the
    wire while suggesting a protection that is not there. What actually guards
    this exchange is a single-use state held in shared storage, an HMAC-signed
    cookie bound to that same state, an exact redirect URI, and a provider that
    must match the one the handshake started with.
    """

    name = "instagram"
    supports_pkce = False
    #: Read-only. There is no ``instagram_business_content_publish`` here.
    scopes: tuple[str, ...] = ("instagram_business_basic",)

    _AUTHORIZE_URL = "https://www.instagram.com/oauth/authorize"
    _TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    _GRAPH_URL = "https://graph.instagram.com/v21.0"

    def build_authorization_url(
        self, *, state: str, code_challenge: str, redirect_uri: str
    ) -> str:
        del code_challenge
        query = httpx.QueryParams(
            {
                "client_id": settings.instagram_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": ",".join(self.scopes),
                "state": state,
            }
        )
        return f"{self._AUTHORIZE_URL}?{query}"

    async def exchange_authorization_code(
        self, *, code: str, code_verifier: str, redirect_uri: str
    ) -> ProviderToken:
        del code_verifier
        form = {
            "client_id": settings.instagram_client_id,
            "client_secret": settings.instagram_client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        }
        async with _client() as client:
            short_lived = await self._post(client, self._TOKEN_URL, form)
            access_token = short_lived.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise SocialProviderError(ERROR_INVALID_GRANT)
            granted = short_lived.get("permissions")
            scopes = self._normalize_scopes(granted)
            # Trade the one-hour token for the 60 day one immediately. Doing it
            # later would mean storing a credential we already know expires
            # before the user is likely to come back.
            long_lived = await self._get(
                client,
                f"{self._GRAPH_URL.rsplit('/', 1)[0]}/access_token",
                {
                    "grant_type": "ig_exchange_token",
                    "client_secret": settings.instagram_client_secret,
                    "access_token": access_token,
                },
            )
        exchanged = long_lived.get("access_token")
        expires_in = long_lived.get("expires_in")
        if isinstance(exchanged, str) and exchanged:
            access_token = exchanged
        expires_at = None
        if isinstance(expires_in, int | float) and expires_in > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        return ProviderToken(
            access_token=access_token,
            refresh_token=None,
            expires_at=expires_at,
            granted_scopes=scopes or self.scopes,
        )

    async def resolve_owned_accounts(self, *, access_token: str) -> tuple[OwnedAccount, ...]:
        async with _client() as client:
            payload = await self._get(
                client,
                f"{self._GRAPH_URL}/me",
                {"fields": "id,username,account_type", "access_token": access_token},
            )
        account_id = payload.get("id")
        username = payload.get("username")
        if not isinstance(account_id, str) or not account_id:
            raise SocialProviderError(ERROR_NO_ELIGIBLE_ACCOUNT)
        return (
            OwnedAccount(
                provider_account_id=account_id,
                display_name=(username if isinstance(username, str) and username else account_id),
                account_type=_normalize_account_type(payload.get("account_type")),
            ),
        )

    async def validate_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> ConnectionCheck:
        try:
            accounts = await self.resolve_owned_accounts(access_token=access_token)
        except SocialProviderError as exc:
            if exc.code in {ERROR_TOKEN_EXPIRED}:
                return ConnectionCheck(status="expired", error_code=exc.code)
            if exc.code in {ERROR_TOKEN_REVOKED, ERROR_INVALID_GRANT}:
                return ConnectionCheck(status="revoked", error_code=exc.code)
            if exc.code == ERROR_PROVIDER_UNAVAILABLE:
                return ConnectionCheck(status="degraded", error_code=exc.code)
            return ConnectionCheck(status="error", error_code=exc.code)
        if not any(account.provider_account_id == provider_account_id for account in accounts):
            # The token works but no longer speaks for this account: treat it as
            # revoked rather than quietly repointing the row somewhere else.
            return ConnectionCheck(status="revoked", error_code=ERROR_TOKEN_REVOKED)
        return ConnectionCheck(status="connected")

    async def revoke_connection(
        self, *, access_token: str, provider_account_id: str
    ) -> bool:
        async with _client() as client:
            try:
                response = await client.delete(
                    f"{self._GRAPH_URL}/{provider_account_id}/permissions",
                    params={"access_token": access_token},
                )
            except httpx.HTTPError:
                return False
        return response.status_code < 400

    @staticmethod
    def _normalize_scopes(granted: object) -> tuple[str, ...]:
        if isinstance(granted, str):
            values = [item.strip() for item in granted.split(",")]
        elif isinstance(granted, list):
            values = [str(item).strip() for item in granted]
        else:
            return ()
        return tuple(value for value in values if value)

    @classmethod
    async def _post(
        cls, client: httpx.AsyncClient, url: str, form: dict[str, str]
    ) -> dict[str, object]:
        try:
            response = await client.post(url, data=form)
        except httpx.HTTPError as exc:
            raise SocialProviderError(ERROR_PROVIDER_UNAVAILABLE) from exc
        return cls._payload(response)

    @classmethod
    async def _get(
        cls, client: httpx.AsyncClient, url: str, params: dict[str, str]
    ) -> dict[str, object]:
        try:
            response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise SocialProviderError(ERROR_PROVIDER_UNAVAILABLE) from exc
        return cls._payload(response)

    @staticmethod
    def _payload(response: httpx.Response) -> dict[str, object]:
        """Read a provider answer, or raise a code that says nothing extra."""

        if response.status_code in {401, 403}:
            raise SocialProviderError(ERROR_TOKEN_REVOKED)
        if response.status_code == 400:
            # 400 covers both "this code is spent" and "this token expired".
            # Neither distinction changes what the user has to do, so the
            # narrower reading is not worth parsing an error body for.
            raise SocialProviderError(ERROR_INVALID_GRANT)
        if response.status_code == 429 or response.status_code >= 500:
            raise SocialProviderError(ERROR_PROVIDER_UNAVAILABLE)
        if response.status_code >= 400:
            raise SocialProviderError(ERROR_PROVIDER_ERROR)
        try:
            payload = response.json()
        except ValueError as exc:
            raise SocialProviderError(ERROR_PROVIDER_ERROR) from exc
        if not isinstance(payload, dict):
            raise SocialProviderError(ERROR_PROVIDER_ERROR)
        return payload


#: Networks we acknowledge but have not implemented, and why. The reason code
#: is translated in the UI; it is never a sentence written here.
_UNIMPLEMENTED: dict[str, str] = {
    "tiktok": "requires_platform_approval",
    "x": "requires_paid_plan",
}

#: Catalog order. Stable so the settings screen does not reshuffle itself.
PROVIDER_ORDER = ("instagram", "tiktok", "x", "demo")


def _descriptor(name: str) -> ProviderDescriptor:
    if name in _UNIMPLEMENTED:
        return ProviderDescriptor(
            name=name,
            status=PROVIDER_DISABLED,
            reason_code=_UNIMPLEMENTED[name],
            supports_pkce=False,
            scopes=(),
        )
    if name == "instagram":
        configured = settings.instagram_connections_configured
        provider = InstagramSocialProvider()
    elif name == "demo":
        configured = settings.social_demo_provider_configured
        provider = DemoSocialProvider()
    else:  # pragma: no cover - PROVIDER_ORDER is closed
        raise KeyError(name)
    return ProviderDescriptor(
        name=name,
        status=PROVIDER_AVAILABLE if configured else PROVIDER_UNCONFIGURED,
        reason_code=None if configured else "not_configured",
        supports_pkce=provider.supports_pkce,
        scopes=provider.scopes,
    )


def provider_catalog() -> tuple[ProviderDescriptor, ...]:
    """Every network the UI may render, with its status right now.

    The demo entry is omitted entirely when it is not usable, so staging and
    production never show a connectable network that does not exist.
    """

    descriptors = []
    for name in PROVIDER_ORDER:
        if name == "demo" and not settings.social_demo_provider_configured:
            continue
        descriptors.append(_descriptor(name))
    return tuple(descriptors)


def descriptor_for(name: str) -> ProviderDescriptor | None:
    """The descriptor for ``name``, or ``None`` if we do not know the network."""

    if name not in PROVIDER_ORDER:
        return None
    if name == "demo" and not settings.social_demo_provider_configured:
        # Outside development the demo provider is not merely unconfigured: it
        # does not exist, and saying so is the point.
        return None
    return _descriptor(name)


def build_provider(name: str) -> SocialConnectionProvider | None:
    """The implementation for ``name``, or ``None`` when it cannot be used.

    There is no fallback. A provider that is unconfigured, disabled or unknown
    yields nothing, and the caller reports that instead of quietly connecting
    the user to a different network.
    """

    descriptor = descriptor_for(name)
    if descriptor is None or descriptor.status != PROVIDER_AVAILABLE:
        return None
    if name == "instagram":
        return InstagramSocialProvider()
    if name == "demo":
        return DemoSocialProvider()
    return None


def redirect_uri_for(name: str) -> str:
    """The exact redirect URI registered for ``name``.

    The browser never supplies this. It is configuration, it is compared byte
    for byte at exchange time, and it is the reason a stolen authorization code
    cannot be redeemed anywhere else.
    """

    if name == "instagram":
        return settings.instagram_redirect_uri
    return f"{settings.social_public_backend_url}{settings.api_prefix}/social/{name}/callback"
