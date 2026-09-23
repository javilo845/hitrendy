"""Short-lived signed access to a generated image.

A signed URL is derived, never stored: it is an HMAC over the asset id, the
owning workspace and an absolute expiry, keyed with the application secret.
Nothing about it is persisted, so a database dump cannot yield a working link,
and rotating the secret invalidates every outstanding link at once.

The signature is compared with :func:`hmac.compare_digest`, and the payload is
rebuilt from the request parameters, so a client can neither extend an expiry
nor point a valid signature at another workspace's asset.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import AppError

_SEPARATOR = "|"
_VERSION = "v1"


@dataclass(frozen=True)
class SignedImageUrl:
    """The temporary link handed to a browser, plus when it dies."""

    url: str
    expires_at: datetime


def _payload(*, asset_id: str, workspace_id: str, expires: int) -> str:
    return _SEPARATOR.join((_VERSION, workspace_id, asset_id, str(expires)))


def _sign(payload: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_image_url(
    *,
    asset_id: str,
    workspace_id: str,
    now: datetime | None = None,
    ttl_seconds: int | None = None,
) -> SignedImageUrl:
    """Mint a temporary link for one asset owned by one workspace."""

    moment = now or datetime.now(UTC)
    ttl = ttl_seconds if ttl_seconds is not None else settings.image_signed_url_ttl_seconds
    expires = int(moment.timestamp()) + ttl
    signature = _sign(_payload(asset_id=asset_id, workspace_id=workspace_id, expires=expires))
    url = (
        f"{settings.api_prefix}/images/files/{asset_id}"
        f"?workspace={workspace_id}&expires={expires}&signature={signature}"
    )
    return SignedImageUrl(url=url, expires_at=datetime.fromtimestamp(expires, tz=UTC))


def verify_image_url(
    *,
    asset_id: str,
    workspace_id: str,
    expires: str | int | None,
    signature: str | None,
    now: datetime | None = None,
) -> None:
    """Raise unless the signature is authentic and still inside its window."""

    moment = now or datetime.now(UTC)
    if not signature or expires is None:
        raise invalid_image_link()
    try:
        deadline = int(expires)
    except (TypeError, ValueError) as exc:
        raise invalid_image_link() from exc
    expected = _sign(_payload(asset_id=asset_id, workspace_id=workspace_id, expires=deadline))
    # Compare before checking the clock so an attacker cannot use the response
    # time to tell an expired signature from a forged one.
    authentic = hmac.compare_digest(expected, signature)
    if not authentic or deadline <= int(moment.timestamp()):
        raise invalid_image_link()


def invalid_image_link() -> AppError:
    # One message for expired and forged alike: the difference is not the
    # caller's business.
    return AppError(
        "IMAGE_LINK_INVALID",
        "Este enlace ya no es válido. Vuelve a abrir la imagen.",
        status_code=403,
    )


# --- Preflight approval -----------------------------------------------------
#
# The confirmation step must prove that *this* user approved *this* exact brief
# and format, recently. The approval is a signature over the request, not a
# stored row: it cannot be replayed against a different brief, cannot be
# extended, and leaves nothing behind if the user abandons the flow.

_APPROVAL_VERSION = "preflight-v1"


@dataclass(frozen=True)
class PreflightApproval:
    token: str
    expires_at: datetime


def _approval_payload(*, workspace_id: str, request_hash: str, expires: int) -> str:
    return _SEPARATOR.join((_APPROVAL_VERSION, workspace_id, request_hash, str(expires)))


def request_fingerprint(
    *,
    prompt: str,
    negative_prompt: str | None,
    aspect_ratio: str,
    reference_asset_id: str | None,
) -> str:
    """Bind an approval to everything the provider will be told.

    The negative prompt is part of the material because it is part of the
    result: a user who approved "avoid crowds" must not have "avoid nothing"
    generated on their budget. Anything that reaches the provider and is not
    covered here would be an editable field the approval does not cover.
    """

    material = _SEPARATOR.join(
        (prompt, negative_prompt or "", aspect_ratio, reference_asset_id or "")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def sign_preflight(
    *, workspace_id: str, request_hash: str, now: datetime | None = None
) -> PreflightApproval:
    moment = now or datetime.now(UTC)
    expires = int(moment.timestamp()) + settings.image_preflight_ttl_seconds
    signature = _sign(
        _approval_payload(workspace_id=workspace_id, request_hash=request_hash, expires=expires)
    )
    return PreflightApproval(
        token=f"{expires}.{signature}",
        expires_at=datetime.fromtimestamp(expires, tz=UTC),
    )


def verify_preflight(
    *,
    workspace_id: str,
    request_hash: str,
    token: str | None,
    now: datetime | None = None,
) -> None:
    """Raise unless the token approves exactly this request and is still fresh."""

    moment = now or datetime.now(UTC)
    if not token or "." not in token:
        raise _approval_invalid()
    raw_expires, _, signature = token.partition(".")
    try:
        deadline = int(raw_expires)
    except ValueError as exc:
        raise _approval_invalid() from exc
    expected = _sign(
        _approval_payload(workspace_id=workspace_id, request_hash=request_hash, expires=deadline)
    )
    authentic = hmac.compare_digest(expected, signature)
    if not authentic or deadline <= int(moment.timestamp()):
        raise _approval_invalid()


def _approval_invalid() -> AppError:
    return AppError(
        "IMAGE_PREFLIGHT_REQUIRED",
        "Revisa y confirma el resumen antes de generar la imagen.",
        status_code=409,
    )
