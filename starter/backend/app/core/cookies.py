from __future__ import annotations

from datetime import timedelta
from typing import Literal

from fastapi import Response

from app.core.config import settings

SESSION_COOKIE = settings.session_cookie_name
SIGNUP_COOKIE = "hitrendy_signup"
OAUTH_COOKIE = "hitrendy_google_oauth"
SOCIAL_OAUTH_COOKIE = "hitrendy_social_oauth"
CSRF_COOKIE = "hitrendy_csrf"

SIGNUP_TTL = timedelta(hours=24)


def _cookie_domain() -> str | None:
    return None


def _cookie_secure() -> bool:
    return settings.app_env not in {"development", "test"}


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    if settings.app_env == "development":
        return "lax"
    return "strict"


def _csrf_cookie_samesite() -> Literal["lax", "strict", "none"]:
    if settings.app_env == "development":
        return "lax"
    return "strict"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        domain=_cookie_domain(),
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        domain=_cookie_domain(),
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        httponly=True,
    )


def set_signup_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SIGNUP_COOKIE,
        value=token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=int(SIGNUP_TTL.total_seconds()),
        path="/",
        domain=_cookie_domain(),
    )


def delete_signup_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SIGNUP_COOKIE,
        path="/",
        domain=_cookie_domain(),
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        httponly=True,
    )


def set_oauth_cookie(response: Response, *, state: str, code_verifier: str) -> None:
    import hashlib
    import hmac

    payload = f"{state}.{code_verifier}"
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    value = f"{payload}.{signature}"
    response.set_cookie(
        key=OAUTH_COOKIE,
        value=value,
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=settings.google_oauth_state_ttl_seconds,
        path=_oauth_cookie_path(),
        domain=_cookie_domain(),
    )


def delete_oauth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=OAUTH_COOKIE,
        path=_oauth_cookie_path(),
        domain=_cookie_domain(),
        secure=_cookie_secure(),
        samesite="lax",
        httponly=True,
    )


def read_oauth_cookie(value: str | None) -> tuple[str, str] | None:
    import hashlib
    import hmac

    if not value:
        return None
    try:
        state, code_verifier, signature = value.split(".", 2)
    except ValueError:
        return None
    expected_payload = f"{state}.{code_verifier}"
    expected = hmac.new(
        settings.jwt_secret.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return state, code_verifier


def set_social_oauth_cookie(response: Response, *, state: str) -> None:
    """Bind a social handshake to the browser that started it.

    The session cookie cannot do this job: outside development it is
    ``SameSite=strict``, so it is not sent on the cross-site redirect back from
    the provider. This one is ``lax`` on purpose, which is why it carries as
    little as possible -- only the ``state``, signed so it cannot be forged.

    The PKCE verifier is deliberately *not* here. It stays in the ephemeral store
    on the server, where a browser can neither read it nor replace it.
    """

    import hashlib
    import hmac

    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"), state.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    response.set_cookie(
        key=SOCIAL_OAUTH_COOKIE,
        value=f"{state}.{signature}",
        httponly=True,
        secure=_cookie_secure(),
        samesite="lax",
        max_age=settings.social_oauth_state_ttl_seconds,
        path=_social_oauth_cookie_path(),
        domain=_cookie_domain(),
    )


def delete_social_oauth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SOCIAL_OAUTH_COOKIE,
        path=_social_oauth_cookie_path(),
        domain=_cookie_domain(),
        secure=_cookie_secure(),
        samesite="lax",
        httponly=True,
    )


def read_social_oauth_cookie(value: str | None) -> str | None:
    """Return the ``state`` this browser was given, or ``None``.

    An unsigned, truncated or altered cookie is indistinguishable from no cookie
    at all: in both cases the callback did not come from a handshake we started.
    """

    import hashlib
    import hmac

    if not value:
        return None
    state, separator, signature = value.rpartition(".")
    if not separator or not state:
        return None
    expected = hmac.new(
        settings.jwt_secret.encode("utf-8"), state.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    return state


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        httponly=False,
        secure=_cookie_secure(),
        samesite=_csrf_cookie_samesite(),
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        domain=_cookie_domain(),
    )


def delete_csrf_cookie(response: Response) -> None:
    response.delete_cookie(
        key=CSRF_COOKIE,
        path="/",
        domain=_cookie_domain(),
        secure=_cookie_secure(),
        samesite=_csrf_cookie_samesite(),
        httponly=False,
    )


def _oauth_cookie_path() -> str:
    return f"{settings.api_prefix}/auth/google"


def _social_oauth_cookie_path() -> str:
    return f"{settings.api_prefix}/social"
