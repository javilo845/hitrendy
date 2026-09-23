"""Durable state for a connected social account.

One table, ``social_connections``, and the interesting part of it is what it
refuses to hold. There is no authorization code, no PKCE verifier, no ``state``
and no cookie: those belong to a single handshake that either finishes in a few
minutes or is worthless, and they live in the ephemeral store for exactly that
long. There is no stored provider response either -- a raw payload carries
e-mail addresses, follower graphs and occasionally other people's data, none of
which this feature needs to name an account in a settings list.

What remains is the minimum required to speak for an account the user owns: the
external id the provider issued, the public handle to show, the scopes that were
actually granted, and the tokens -- encrypted, never in plaintext, and always
through :mod:`app.social.crypto`.

The status column is the honest answer to "does this connection still work?".
It is written from what the provider said, not from what the user hoped::

    connected -> expired | revoked | degraded | error -> disconnected

``disconnected`` is terminal and is the only state in which the row keeps no
token at all. The row itself survives disconnection on purpose: the unique
constraint is what stops the same account from being connected twice, and a
reconnect must land on the existing row rather than racing to insert a second
one.

Two statuses that the HTTP layer reports are deliberately absent here:
``unconfigured`` and ``disabled`` describe a *provider* in this deployment, not
an account, and persisting them would be storing a copy of the configuration.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: Every state a stored connection may be in.
CONNECTION_STATUSES = (
    "connected",
    "expired",
    "revoked",
    "degraded",
    "error",
    "disconnected",
)

#: States in which the stored token is still worth trying. Anything else needs a
#: fresh handshake, so the UI offers "reconnect" instead of "check".
USABLE_CONNECTION_STATUSES = frozenset({"connected", "degraded"})

#: The end of the line. A row here holds no credential material whatsoever.
TERMINAL_CONNECTION_STATUS = "disconnected"

#: The shapes of account a provider may report. ``unknown`` exists so an
#: unfamiliar value from a provider is recorded as unfamiliar rather than
#: guessed at.
ACCOUNT_TYPES = ("business", "creator", "personal", "unknown")


def _uuid() -> str:
    return uuid.uuid4().hex


class SocialConnection(Base):
    """A social account this workspace has proven it controls."""

    __tablename__ = "social_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    #: The id the provider issued. Never accepted from the browser: it is read
    #: back from the provider with the token that was just exchanged.
    provider_account_id: Mapped[str] = mapped_column(String(191), nullable=False)
    #: The public handle, shown so the user can tell two accounts apart. Not the
    #: person's name and not their e-mail.
    display_name: Mapped[str] = mapped_column(String(191), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unknown"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="connected")
    #: AES-256-GCM envelopes, bound to this workspace and provider by associated
    #: data. ``Text`` because an envelope has no useful upper bound and silently
    #: truncating one would destroy the credential.
    encrypted_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: What the provider actually granted, space separated. Stored so the server
    #: can tell a missing capability from a broken token without asking again.
    granted_scopes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: A normalised code from :mod:`app.social.providers`, never a provider error
    #: body: those quote request URLs, tokens and internal identifiers.
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # One row per external account per provider per workspace. This is what
        # makes a repeated handshake an update instead of a duplicate, and it is
        # scoped to the workspace so two workspaces may connect the same account
        # without either learning about the other.
        UniqueConstraint(
            "workspace_id",
            "provider",
            "provider_account_id",
            name="uq_social_connection_account",
        ),
        # The listing always reads one workspace, usually filtered by provider.
        Index("ix_social_connections_workspace_provider", "workspace_id", "provider"),
        CheckConstraint(
            "status IN ('connected', 'expired', 'revoked', "
            "'degraded', 'error', 'disconnected')",
            name="ck_social_connection_status",
        ),
        CheckConstraint(
            "account_type IN ('business', 'creator', 'personal', 'unknown')",
            name="ck_social_connection_account_type",
        ),
        # A connection the UI presents as working must actually hold a token.
        # Without this, a failed write could leave a row that looks connected and
        # fails on first use.
        CheckConstraint(
            "status <> 'connected' OR encrypted_access_token IS NOT NULL",
            name="ck_social_connection_connected_token",
        ),
        # Disconnection is not a label. The credential is gone, or the row is not
        # disconnected; the database is the last place that can insist on this.
        CheckConstraint(
            "status <> 'disconnected' OR ("
            "encrypted_access_token IS NULL AND encrypted_refresh_token IS NULL"
            ")",
            name="ck_social_connection_disconnected_tokens",
        ),
        CheckConstraint(
            "status <> 'disconnected' OR disconnected_at IS NOT NULL",
            name="ck_social_connection_disconnected_at",
        ),
    )
