"""Domain-separated signatures for video links and preflight approvals."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.errors import AppError

_VIDEO_URL_DOMAIN = "hitrendy-video-url-v1"
_VIDEO_PREFLIGHT_DOMAIN = "hitrendy-video-preflight-v1"


def _expiry_timestamp(expires_at: datetime | int | str) -> int:
    if isinstance(expires_at, datetime):
        moment = expires_at if expires_at.tzinfo is not None else expires_at.replace(tzinfo=UTC)
        return int(moment.timestamp())
    return int(expires_at)


def _sign(domain: str, *parts: str) -> str:
    payload = "|".join((domain, *parts))
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign_video_url(asset_id: str, workspace_id: str, expires_at: datetime | int) -> str:
    """Sign one asset/workspace/expiry tuple with the video-only domain."""

    expires = _expiry_timestamp(expires_at)
    return _sign(_VIDEO_URL_DOMAIN, workspace_id, asset_id, str(expires))


def verify_video_url(
    asset_id: str,
    workspace_id: str,
    expires_at: datetime | int | str,
    signature: str | None,
    *,
    now: datetime | None = None,
) -> None:
    """Reject forged or expired signatures without exposing a timing oracle."""

    try:
        expires = _expiry_timestamp(expires_at)
    except (TypeError, ValueError, OverflowError) as exc:
        raise invalid_video_link() from exc
    expected = _sign(_VIDEO_URL_DOMAIN, workspace_id, asset_id, str(expires))
    authentic = isinstance(signature, str) and hmac.compare_digest(expected, signature)
    if not authentic:
        raise invalid_video_link()
    moment = now or datetime.now(UTC)
    if expires <= int(moment.timestamp()):
        raise invalid_video_link()


def request_fingerprint(
    *,
    prompt: str,
    negative_prompt: str | None,
    storyboard: Mapping[str, Any] | Any,
    aspect_ratio: str,
    duration_seconds: int,
    source_asset_id: str | None,
    project_id: str | None,
) -> str:
    """Hash every editable field that can reach a video provider."""

    if hasattr(storyboard, "model_dump"):
        storyboard = storyboard.model_dump(mode="json")
    material = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "storyboard": storyboard,
        "aspect_ratio": aspect_ratio,
        "duration_seconds": duration_seconds,
        "source_asset_id": source_asset_id,
        "project_id": project_id,
    }
    canonical = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sign_preflight(fingerprint: str, workspace_id: str, expires_at: datetime | int) -> str:
    """Sign an exact, short-lived video preflight approval."""

    expires = _expiry_timestamp(expires_at)
    return _sign(_VIDEO_PREFLIGHT_DOMAIN, workspace_id, fingerprint, str(expires))


def verify_preflight(
    fingerprint: str,
    workspace_id: str,
    expires_at: datetime | int | str,
    token: str | None,
    *,
    now: datetime | None = None,
) -> None:
    """Verify the approval signature before evaluating its expiry."""

    try:
        expires = _expiry_timestamp(expires_at)
    except (TypeError, ValueError, OverflowError) as exc:
        raise invalid_video_preflight() from exc
    expected = _sign(_VIDEO_PREFLIGHT_DOMAIN, workspace_id, fingerprint, str(expires))
    authentic = isinstance(token, str) and hmac.compare_digest(expected, token)
    if not authentic:
        raise invalid_video_preflight()
    moment = now or datetime.now(UTC)
    if expires <= int(moment.timestamp()):
        raise invalid_video_preflight()


def invalid_video_link() -> AppError:
    return AppError(
        "VIDEO_LINK_INVALID",
        "Este enlace de video ya no es válido.",
        status_code=403,
    )


def invalid_video_preflight() -> AppError:
    return AppError(
        "VIDEO_PREFLIGHT_REQUIRED",
        "Revisa y confirma el resumen antes de generar el video.",
        status_code=409,
    )
