from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, ForbiddenError
from app.db.session import get_db as _get_db
from app.identity.models import AuthSession, User, WorkspaceMember

WORKSPACE_HEADER = "X-Workspace-Id"


@dataclass(frozen=True)
class CurrentPrincipal:
    user: dict[str, str]
    session: AuthSession
    workspaces: list[dict[str, str]]


async def get_db():
    async for session in _get_db():
        yield session


async def get_current_principal(
    session_token: str | None = Cookie(None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> CurrentPrincipal:
    if not session_token:
        raise AppError("UNAUTHENTICATED", "Inicia sesión para continuar.", status_code=401)
    from hashlib import sha256

    result = await db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_hash == sha256(session_token.encode("utf-8")).hexdigest(),
            User.status == "active",
        )
    )
    row = result.one_or_none()
    if row is None or row.AuthSession.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
        raise AppError("UNAUTHENTICATED", "Inicia sesión para continuar.", status_code=401)
    memberships = await db.execute(
        select(WorkspaceMember).where(WorkspaceMember.user_id == row.User.id)
    )
    workspaces = [
        {"id": member.workspace_id, "role": member.role} for member in memberships.scalars().all()
    ]
    return CurrentPrincipal(
        user={"id": row.User.id, "name": row.User.name, "email": row.User.email},
        session=row.AuthSession,
        workspaces=workspaces,
    )


async def require_workspace(
    x_workspace_id: str | None = Header(None, alias=WORKSPACE_HEADER),
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> str:
    workspace_id = x_workspace_id or (
        principal.workspaces[0]["id"] if principal.workspaces else None
    )
    if not workspace_id or workspace_id not in {
        workspace["id"] for workspace in principal.workspaces
    }:
        raise ForbiddenError()
    return workspace_id
