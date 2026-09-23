from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import httpx

from app.core.config import settings

logger = logging.getLogger("hitrendy.email")


@dataclass(frozen=True)
class EmailMessage:
    recipient: str
    subject: str
    text: str
    kind: str


class EmailSender(Protocol):
    provider_name: str

    async def send_password_reset(
        self, *, recipient: str, reset_url: str, expires_at: datetime
    ) -> None:
        """Deliver a recovery link without returning the raw token to a route."""


class DisabledEmailSender:
    provider_name = "disabled"

    async def send_password_reset(
        self, *, recipient: str, reset_url: str, expires_at: datetime
    ) -> None:
        del recipient, reset_url, expires_at
        raise RuntimeError("El correo transaccional no está configurado.")


_demo_messages: list[EmailMessage] = []


class DemoEmailSender:
    """Deterministic local adapter; it never sends a network request."""

    provider_name = "demo"

    async def send_password_reset(
        self, *, recipient: str, reset_url: str, expires_at: datetime
    ) -> None:
        _demo_messages.append(
            EmailMessage(
                recipient=recipient,
                subject="Restablece tu contraseña de HiTrendy",
                text=(
                    "Recibimos una solicitud para cambiar tu contraseña. "
                    f"Abre este enlace antes de {expires_at.isoformat()}: {reset_url}\n\n"
                    "Si no fuiste tú, ignora este mensaje."
                ),
                kind="password_reset",
            )
        )


class ResendEmailSender:
    """Small Resend adapter kept behind the email interface."""

    provider_name = "resend"

    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def send_password_reset(
        self, *, recipient: str, reset_url: str, expires_at: datetime
    ) -> None:
        payload = {
            "from": self._sender,
            "to": [recipient],
            "subject": "Restablece tu contraseña de HiTrendy",
            "text": (
                "Recibimos una solicitud para cambiar tu contraseña. "
                f"Abre este enlace antes de {expires_at.isoformat()}: {reset_url}\n\n"
                "Si no fuiste tú, ignora este mensaje."
            ),
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("La entrega del correo falló.") from exc


def demo_messages() -> tuple[EmailMessage, ...]:
    """Return a read-only snapshot for deterministic tests and local tools."""

    return tuple(_demo_messages)


def clear_demo_messages() -> None:
    _demo_messages.clear()


def get_email_sender() -> EmailSender:
    if settings.email_provider == "demo":
        return DemoEmailSender()
    if settings.email_provider == "resend":
        return ResendEmailSender(
            api_key=settings.resend_api_key,
            sender=settings.email_from,
            timeout_seconds=settings.email_timeout_seconds,
        )
    return DisabledEmailSender()

