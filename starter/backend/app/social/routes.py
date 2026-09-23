"""HTTP surface for social connections.

Five endpoints, and the shape of the set is the point: one to list, one to start
a handshake, one for the provider to return to, one to re-check a connection, and
one to remove it.

There is no sixth endpoint that publishes anything, and there is nowhere in this
module that accepts an account id, a scope, a redirect URI or a provider
endpoint from the caller. The browser may name a *provider* and a connection id
it already owns; everything else is server state.

The callback is the only route here that answers an unauthenticated request. It
never returns a body, only a redirect to an internal path, and every failure --
forged state, expired state, replayed state, wrong provider, denied consent --
produces the same neutral outcome.
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Path, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cookies import (
    SOCIAL_OAUTH_COOKIE,
    delete_social_oauth_cookie,
    read_social_oauth_cookie,
    set_social_oauth_cookie,
)
from app.dependencies import CurrentPrincipal, get_current_principal, get_db, require_workspace
from app.social import service

router = APIRouter(prefix="/social", tags=["social"])

#: Provider names are short server-defined slugs. The pattern is what keeps a
#: path, a host or a scheme out of the one path parameter the caller controls.
_PROVIDER_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"

#: Connection ids are opaque server-generated hex.
_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class AuthorizeRequest(BaseModel):
    """The only thing a client may ask for: where to come back to.

    Not the provider's endpoint, not the redirect URI, not the scopes, not the
    account. A ``return_path`` that is not a plain internal path is silently
    replaced by the default.
    """

    return_path: str | None = Field(None, max_length=200)


@router.get("/connections")
async def list_social_connections(
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Every provider this deployment knows about, plus this workspace's rows.

    Answers even when the feature is off, because "off" is exactly what the
    Settings screen has to be able to say.
    """

    return await service.list_connections(db, workspace_id=workspace_id)


@router.post("/{provider}/authorize")
async def start_social_authorization(
    body: AuthorizeRequest,
    response: Response,
    provider: str = Path(pattern=_PROVIDER_PATTERN, max_length=32),
    workspace_id: str = Depends(require_workspace),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> dict:
    """Begin the handshake and hand back the URL to send the user to.

    The server does not redirect here: this is an authenticated ``POST`` behind
    CSRF, and the frontend performs the navigation. The ``state`` is stored twice
    -- server-side with the workspace, the user and the PKCE verifier, and in a
    signed ``SameSite=lax`` cookie that is the only thing the callback will
    accept as proof the browser is the one that started this.
    """

    start = await service.start_authorization(
        workspace_id=workspace_id,
        user_id=principal.user["id"],
        provider_name=provider,
        return_path=body.return_path,
    )
    set_social_oauth_cookie(response, state=start.state)
    return {"provider": provider, "authorization_url": start.authorization_url}


@router.get("/{provider}/callback")
async def complete_social_authorization(
    provider: str = Path(pattern=_PROVIDER_PATTERN, max_length=32),
    code: str | None = Query(None, max_length=4096),
    state: str | None = Query(None, max_length=256),
    # The provider's own error slug. Read only to distinguish "the user said no"
    # from "the request was malformed"; never echoed back to the browser.
    error: str | None = Query(None, max_length=120),
    cookie_state: str | None = Cookie(None, alias=SOCIAL_OAUTH_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Where the provider returns the user. Consumes the handshake exactly once.

    Every parameter is optional so that a malformed callback fails as a rejected
    callback rather than as a schema error: the two must be indistinguishable.
    """

    target = await service.complete_callback(
        db,
        provider_name=provider,
        code=code,
        state=state,
        cookie_state=read_social_oauth_cookie(cookie_state),
        provider_error=error,
    )
    # 303 so the browser follows with GET, and the cookie is cleared whatever the
    # outcome: it is single-use by intent, exactly like the state it carries.
    redirect = RedirectResponse(url=target, status_code=303)
    delete_social_oauth_cookie(redirect)
    return redirect


@router.post("/connections/{connection_id}/check")
async def check_social_connection(
    connection_id: str = Path(pattern=_ID_PATTERN, max_length=64),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ask the provider whether this connection still works, and record it.

    A user-initiated check, not a schedule: nothing in the web process refreshes
    tokens in the background.
    """

    connection = await service.check_connection(
        db, workspace_id=workspace_id, connection_id=connection_id
    )
    return {"connection": service.serialize_connection(connection)}


@router.delete("/connections/{connection_id}")
async def disconnect_social_connection(
    connection_id: str = Path(pattern=_ID_PATTERN, max_length=64),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove the connection. Idempotent, and never permanently blocked.

    A token the network already revoked, or a network that is briefly
    unreachable, still results in the local credential being destroyed.
    """

    connection = await service.disconnect_connection(
        db, workspace_id=workspace_id, connection_id=connection_id
    )
    return {"connection": service.serialize_connection(connection)}
