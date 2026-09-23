"""Application logic for connecting, checking and disconnecting accounts.

The handshake is split in two halves that share nothing but a ``state``:

* ``start_authorization`` runs inside an authenticated request. It knows the
  workspace and the user, and it writes everything the second half will need to
  the ephemeral store -- never to the URL, and never to the browser.
* ``complete_callback`` runs on a cross-site redirect with no session cookie
  available. It trusts nothing the browser sent except a signed cookie holding
  the ``state``, and it recovers the workspace, the user, the provider, the
  redirect URI and the PKCE verifier from the server's own record.

That asymmetry is the whole design. The browser cannot choose the provider it is
connecting to, the account it ends up owning, the URI the code is redeemed
against, or the page it is returned to.

Nothing in this module posts to a network.
"""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFoundError
from app.identity.models import WorkspaceMember
from app.social import crypto, oauth_state, providers
from app.social.models import SocialConnection

#: Where the user lands when the handshake did not carry a usable return path.
DEFAULT_RETURN_PATH = "/settings"

#: A return path is an internal path and nothing else: no scheme, no host, no
#: query, no fragment, no backslash, no double slash. Anything richer is how an
#: open redirect gets built, and none of it is needed to send a user back to a
#: settings screen.
_RETURN_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9/_.-]{0,119}$")

#: The query parameter the frontend reads after a callback.
_OUTCOME_PARAM = "social"
OUTCOME_CONNECTED = "connected"
OUTCOME_ERROR = "error"

#: The only reasons a callback ever reveals. Every rejected state -- forged,
#: expired, replayed, from another session, for another provider -- collapses
#: into ``invalid_request``, because telling them apart would turn the redirect
#: into an oracle.
REASON_INVALID_REQUEST = "invalid_request"
REASON_DENIED = "denied"
REASON_PROVIDER_ERROR = "provider_error"
REASON_UNAVAILABLE = "unavailable"

#: Column widths, enforced here so a long provider value truncates predictably
#: instead of failing the insert.
_ACCOUNT_ID_LIMIT = 191
_DISPLAY_NAME_LIMIT = 191
_SCOPES_LIMIT = 500


@dataclass(frozen=True)
class AuthorizationStart:
    """What the route needs to send the user to the provider."""

    authorization_url: str
    state: str


def _reject_unexpected_scopes(*, granted: tuple[str, ...], requested: tuple[str, ...]) -> None:
    """Refuse a token whose scopes do not match the request.

    A missing scope means the connection would not work. A scope we never asked
    for means holding more authority over someone's account than the consent
    screen described -- in a wave that does not publish, possibly a publishing
    permission. Neither is stored.

    Silence is accepted: several providers do not report scopes at all, and
    absence is not evidence of extra authority. What is reported is checked
    strictly.
    """

    granted_set = {scope for scope in granted if scope}
    requested_set = {scope for scope in requested if scope}
    if granted_set and granted_set != requested_set:
        raise providers.SocialProviderError(providers.ERROR_UNEXPECTED_SCOPE)


def safe_return_path(candidate: str | None) -> str:
    """Return an internal path we are willing to redirect to.

    Rejection is silent and falls back to the default: a caller that asked for
    somewhere else does not get told whether the attempt was noticed.
    """

    value = (candidate or "").strip()
    if not value or value.startswith("//") or ".." in value:
        return DEFAULT_RETURN_PATH
    if not _RETURN_PATH_PATTERN.match(value):
        return DEFAULT_RETURN_PATH
    return value


def provider_unavailable_error() -> AppError:
    """A provider this deployment cannot complete a handshake with."""

    return AppError(
        "SOCIAL_PROVIDER_UNAVAILABLE",
        "Este proveedor no está disponible en esta instalación.",
        status_code=409,
    )


def public_status(connection: SocialConnection, *, now: datetime | None = None) -> str:
    """The status to show, which is not always the status stored.

    A token with a known past expiry is reported as ``expired`` even before
    anybody asks the provider. Waiting for a check to say so would mean showing
    a green connection we already know is dead.
    """

    if connection.status != "connected":
        return connection.status
    if connection.token_expires_at is None:
        return connection.status
    expires_at = connection.token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= (now or datetime.now(UTC)):
        return "expired"
    return connection.status


def serialize_connection(connection: SocialConnection) -> dict:
    """The public shape of a connection.

    Every omission is deliberate. There is no token, no envelope, no scope the
    provider refused, no provider payload and no error body -- only a normalized
    code the UI can translate.
    """

    return {
        "id": connection.id,
        "provider": connection.provider,
        "display_name": connection.display_name,
        "account_type": connection.account_type,
        "status": public_status(connection),
        "connected_at": (
            connection.connected_at.isoformat() if connection.connected_at else None
        ),
        "last_checked_at": (
            connection.last_checked_at.isoformat() if connection.last_checked_at else None
        ),
        "safe_error": connection.last_error_code,
    }


def serialize_provider(descriptor: providers.ProviderDescriptor) -> dict:
    return {
        "name": descriptor.name,
        "status": descriptor.status,
        "reason_code": descriptor.reason_code,
    }


async def list_connections(db: AsyncSession, *, workspace_id: str) -> dict:
    """Every provider this deployment knows about, plus this workspace's rows."""

    rows = await db.execute(
        select(SocialConnection)
        .where(SocialConnection.workspace_id == workspace_id)
        .order_by(SocialConnection.provider, SocialConnection.created_at)
    )
    connections = list(rows.scalars().all())
    return {
        "enabled": settings.social_connections_enabled,
        "providers": [serialize_provider(item) for item in providers.provider_catalog()],
        "connections": [serialize_connection(item) for item in connections],
    }


async def start_authorization(
    *,
    workspace_id: str,
    user_id: str,
    provider_name: str,
    return_path: str | None,
) -> AuthorizationStart:
    """Begin a handshake and remember it server-side."""

    descriptor = providers.descriptor_for(provider_name)
    if descriptor is None:
        # An unknown network and a network that does not exist here are the same
        # answer: there is nothing to connect.
        raise NotFoundError("Proveedor")
    provider = providers.build_provider(provider_name)
    if provider is None:
        raise provider_unavailable_error()
    if not crypto.encryption_available():
        # Refusing to start is the only safe answer: the handshake would end with
        # a token we cannot store safely.
        raise crypto.cipher_unavailable_error()

    redirect_uri = providers.redirect_uri_for(provider_name)
    if not redirect_uri:
        raise provider_unavailable_error()

    state = oauth_state.create_state()
    code_verifier = oauth_state.create_code_verifier()
    # The verifier is generated either way and stays server-side. For a provider
    # without PKCE the challenge is simply never put on the wire.
    code_challenge = (
        oauth_state.create_code_challenge(code_verifier) if provider.supports_pkce else ""
    )
    await oauth_state.remember(
        state=state,
        provider=provider_name,
        workspace_id=workspace_id,
        user_id=user_id,
        code_verifier=code_verifier,
        redirect_uri=redirect_uri,
        return_path=safe_return_path(return_path),
        scopes=tuple(provider.scopes),
    )
    authorization_url = provider.build_authorization_url(
        state=state, code_challenge=code_challenge, redirect_uri=redirect_uri
    )
    return AuthorizationStart(authorization_url=authorization_url, state=state)


def callback_redirect(
    *, return_path: str, outcome: str, provider_name: str | None = None, reason: str | None = None
) -> str:
    """Build the internal URL the callback sends the browser to.

    The host comes from configuration and the path has already been validated,
    so this function cannot produce a link that leaves the application no matter
    what the provider echoed back.
    """

    params: dict[str, str] = {_OUTCOME_PARAM: outcome}
    if provider_name:
        params["provider"] = provider_name
    if reason:
        params["reason"] = reason
    return f"{settings.frontend_url}{safe_return_path(return_path)}?{urlencode(params)}"


async def complete_callback(
    db: AsyncSession,
    *,
    provider_name: str,
    code: str | None,
    state: str | None,
    cookie_state: str | None,
    provider_error: str | None,
) -> str:
    """Finish a handshake, or send the user back with a neutral failure.

    Returns the URL to redirect to. It never raises for a bad callback: an
    attacker-controlled request must not be able to tell a rejected state from a
    missing one, and an error page would say more than a redirect does.
    """

    # The cookie is checked before the state is consumed. Otherwise anyone who
    # learned a state value could burn it without holding the browser that
    # started the handshake.
    if (
        not state
        or not cookie_state
        # Compared as bytes: a cookie is attacker-supplied text and
        # ``compare_digest`` rejects non-ASCII ``str`` with a ``TypeError``.
        or not hmac.compare_digest(state.encode("utf-8"), cookie_state.encode("utf-8"))
    ):
        return callback_redirect(
            return_path=DEFAULT_RETURN_PATH,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_INVALID_REQUEST,
        )

    authorization, _reason = await oauth_state.consume(state=state)
    if authorization is None or authorization.provider != provider_name:
        # ``_reason`` distinguishes expired from replayed from forged. It stays
        # internal on purpose.
        return callback_redirect(
            return_path=DEFAULT_RETURN_PATH,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_INVALID_REQUEST,
        )

    return_path = authorization.return_path
    if provider_error:
        # The user said no at the provider, or the provider refused. Either way
        # its own message is not repeated back.
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_DENIED,
        )
    if not code:
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_INVALID_REQUEST,
        )

    try:
        member = await db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == authorization.workspace_id,
                WorkspaceMember.user_id == authorization.user_id,
            )
        )
    except SQLAlchemyError:
        await db.rollback()
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_PROVIDER_ERROR,
        )
    if member is None:
        # Access was removed between the two halves of the handshake. The state
        # was valid; the authority behind it no longer is.
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_INVALID_REQUEST,
        )

    provider = providers.build_provider(provider_name)
    if provider is None or not crypto.encryption_available():
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_UNAVAILABLE,
        )

    try:
        token = await provider.exchange_authorization_code(
            code=code,
            code_verifier=authorization.code_verifier,
            # The stored URI, not one the browser could influence.
            redirect_uri=authorization.redirect_uri,
        )
        _reject_unexpected_scopes(granted=token.granted_scopes, requested=authorization.scopes)
        accounts = await provider.resolve_owned_accounts(access_token=token.access_token)
    except providers.SocialProviderError:
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_PROVIDER_ERROR,
        )
    if not accounts:
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_PROVIDER_ERROR,
        )

    if len(accounts) > 1:
        # Demo e Instagram, los dos proveedores de esta ola, devuelven exactamente una cuenta.
        # Ningún proveedor de esta ola devuelve más de una cuenta.
        # Conectar varias en silencio elegiría por el usuario; conectar la primera elegiría peor.
        # Se rechaza entero.
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_PROVIDER_ERROR,
        )

    account = accounts[0]
    try:
        connection = await _upsert_connection(
            db,
            workspace_id=authorization.workspace_id,
            provider_name=provider_name,
            account=account,
            token=token,
        )
        if connection is None:
            await db.rollback()
            return callback_redirect(
                return_path=return_path,
                outcome=OUTCOME_ERROR,
                provider_name=provider_name,
                reason=REASON_PROVIDER_ERROR,
            )
        await db.commit()
    except SQLAlchemyError:
        await db.rollback()
        return callback_redirect(
            return_path=return_path,
            outcome=OUTCOME_ERROR,
            provider_name=provider_name,
            reason=REASON_PROVIDER_ERROR,
        )
    return callback_redirect(
        return_path=return_path,
        outcome=OUTCOME_CONNECTED,
        provider_name=provider_name,
    )


async def _upsert_connection(
    db: AsyncSession,
    *,
    workspace_id: str,
    provider_name: str,
    account: providers.OwnedAccount,
    token: providers.ProviderToken,
) -> SocialConnection | None:
    """Create or refresh the single row for this workspace/provider/account."""

    provider_account_id = account.provider_account_id[:_ACCOUNT_ID_LIMIT]
    connection = await db.scalar(
        select(SocialConnection).where(
            SocialConnection.workspace_id == workspace_id,
            SocialConnection.provider == provider_name,
            SocialConnection.provider_account_id == provider_account_id,
        )
    )
    if connection is None:
        try:
            async with db.begin_nested():
                connection = SocialConnection(
                    workspace_id=workspace_id,
                    provider=provider_name,
                    provider_account_id=provider_account_id,
                )
                db.add(connection)
                _apply_connection_values(
                    connection,
                    workspace_id=workspace_id,
                    provider_name=provider_name,
                    provider_account_id=provider_account_id,
                    account=account,
                    token=token,
                )
                await db.flush()
            return connection
        except IntegrityError:
            # The unique constraint arbitrates two callbacks that both missed the
            # fast path. The failed INSERT is isolated to the savepoint, so the
            # outer transaction can safely re-read and refresh the winner.
            connection = await db.scalar(
                select(SocialConnection)
                .where(
                    SocialConnection.workspace_id == workspace_id,
                    SocialConnection.provider == provider_name,
                    SocialConnection.provider_account_id == provider_account_id,
                )
                .with_for_update()
            )
            if connection is None:
                # There is no safe row to update. Keep the callback neutral rather
                # than exposing a database race as an HTTP failure.
                return None

    _apply_connection_values(
        connection,
        workspace_id=workspace_id,
        provider_name=provider_name,
        provider_account_id=provider_account_id,
        account=account,
        token=token,
    )
    return connection


def _apply_connection_values(
    connection: SocialConnection,
    *,
    workspace_id: str,
    provider_name: str,
    provider_account_id: str,
    account: providers.OwnedAccount,
    token: providers.ProviderToken,
) -> None:
    """Apply the provider result without retaining any provider object."""

    connection.display_name = (account.display_name or provider_account_id)[:_DISPLAY_NAME_LIMIT]
    connection.account_type = (
        account.account_type if account.account_type in providers.ACCOUNT_TYPES else "unknown"
    )
    connection.encrypted_access_token = crypto.encrypt_token(
        token.access_token,
        workspace_id=workspace_id,
        provider=provider_name,
        purpose=crypto.ACCESS_TOKEN_PURPOSE,
    )
    connection.encrypted_refresh_token = (
        crypto.encrypt_token(
            token.refresh_token,
            workspace_id=workspace_id,
            provider=provider_name,
            purpose=crypto.REFRESH_TOKEN_PURPOSE,
        )
        if token.refresh_token
        else None
    )
    connection.token_expires_at = token.expires_at
    connection.granted_scopes = " ".join(token.granted_scopes)[:_SCOPES_LIMIT] or None
    connection.status = "connected"
    connection.last_error_code = None
    connection.last_checked_at = datetime.now(UTC)
    connection.connected_at = datetime.now(UTC)
    # Reconnecting an account that was disconnected before must not leave the
    # old timestamp behind, or the UI would claim it is still disconnected.
    connection.disconnected_at = None


async def get_connection(
    db: AsyncSession, *, workspace_id: str, connection_id: str
) -> SocialConnection:
    """One connection belonging to this workspace.

    A valid id from another workspace raises exactly what a nonexistent id
    raises. Whether a row exists elsewhere is not something a caller may learn.
    """

    connection = await db.scalar(
        select(SocialConnection).where(
            SocialConnection.id == connection_id,
            SocialConnection.workspace_id == workspace_id,
        )
    )
    if connection is None:
        raise NotFoundError("Conexión")
    return connection


def _decrypt_access_token(connection: SocialConnection) -> str | None:
    if not connection.encrypted_access_token:
        return None
    try:
        return crypto.decrypt_token(
            connection.encrypted_access_token,
            workspace_id=connection.workspace_id,
            provider=connection.provider,
            purpose=crypto.ACCESS_TOKEN_PURPOSE,
        )
    except (crypto.TokenDecryptionError, crypto.TokenCipherUnavailable):
        return None


async def check_connection(
    db: AsyncSession, *, workspace_id: str, connection_id: str
) -> SocialConnection:
    """Ask the provider whether the stored token still works, and record it."""

    connection = await get_connection(
        db, workspace_id=workspace_id, connection_id=connection_id
    )
    now = datetime.now(UTC)
    connection.last_checked_at = now

    if connection.status == "disconnected":
        # Nothing to ask about, and no token to ask with.
        await db.commit()
        return connection

    provider = providers.build_provider(connection.provider)
    access_token = _decrypt_access_token(connection)
    if provider is None:
        # The network was turned off, or its credentials were removed, after this
        # row was written. The connection is not broken; we simply cannot verify
        # it right now, and saying so is more useful than guessing.
        connection.status = "degraded"
        connection.last_error_code = providers.ERROR_PROVIDER_UNAVAILABLE
    elif access_token is None:
        # An envelope that will not open is a credential we no longer hold, even
        # if the network still considers it valid.
        connection.status = "error"
        connection.last_error_code = providers.ERROR_TOKEN_UNREADABLE
    else:
        result = await provider.validate_connection(
            access_token=access_token, provider_account_id=connection.provider_account_id
        )
        connection.status = result.status
        connection.last_error_code = result.error_code
        if result.status == "connected" and connection.token_expires_at is not None:
            expires_at = connection.token_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at <= now:
                # The provider still accepts it, but we recorded an expiry that
                # has passed. Trust the provider and clear the stale expiry
                # rather than showing a working connection as dead forever.
                connection.token_expires_at = None
    await db.commit()
    return connection


async def disconnect_connection(
    db: AsyncSession, *, workspace_id: str, connection_id: str
) -> SocialConnection:
    """Revoke where possible, forget locally always.

    Idempotent, and deliberately tolerant: a token the provider already revoked,
    a network that is now unconfigured, or a provider that is briefly down must
    not be able to trap a user with a connection they cannot remove. The local
    credential is destroyed in every one of those cases.
    """

    connection = await get_connection(
        db, workspace_id=workspace_id, connection_id=connection_id
    )
    if connection.status == "disconnected":
        return connection

    provider = providers.build_provider(connection.provider)
    access_token = _decrypt_access_token(connection)
    revoked = False
    if provider is not None and access_token is not None:
        try:
            revoked = await provider.revoke_connection(
                access_token=access_token,
                provider_account_id=connection.provider_account_id,
            )
        except providers.SocialProviderError:
            revoked = False

    now = datetime.now(UTC)
    connection.status = "disconnected"
    connection.encrypted_access_token = None
    connection.encrypted_refresh_token = None
    connection.token_expires_at = None
    connection.granted_scopes = None
    connection.disconnected_at = now
    connection.last_checked_at = now
    # Recorded so the UI can say "removed here, may still appear in the network's
    # own app settings" instead of implying a revocation that did not happen.
    connection.last_error_code = None if revoked else providers.ERROR_REVOKE_UNCONFIRMED
    await db.commit()
    return connection
