from __future__ import annotations

import hashlib
import hmac

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.cookies import CSRF_COOKIE, SIGNUP_COOKIE

CSRF_CONTEXT_SESSION = "session"
CSRF_CONTEXT_SIGNUP = "signup"

def _generate_csrf_token(context_token: str, context: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{context}:{context_token}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _validate_csrf_token(context_token: str, csrf_token: str, context: str) -> bool:
    expected = _generate_csrf_token(context_token, context)
    return hmac.compare_digest(expected, csrf_token)


CSRF_EXEMPT_PATHS: set[str] = {
    "/health/live",
    "/health/ready",
    "/api/v1/auth/csrf",
    "/api/v1/auth/google/callback",
    "/api/v1/auth/google/status",
    "/api/v1/auth/google/start",
}

CSRF_SAFE_METHODS: set[str] = {"GET", "HEAD", "OPTIONS"}


def should_validate_csrf(path: str, method: str) -> bool:
    if method in CSRF_SAFE_METHODS:
        return False
    if path in CSRF_EXEMPT_PATHS:
        return False
    if path.startswith(settings.api_prefix) is False and not path.startswith("/health"):
        return True
    return True


def _pick_context(
    path: str, session_token: str | None, signup_token: str | None
) -> tuple[str, str] | None:
    if session_token:
        return session_token, CSRF_CONTEXT_SESSION
    if signup_token:
        return signup_token, CSRF_CONTEXT_SIGNUP
    return None


async def csrf_middleware(request: Request, call_next):
    if not should_validate_csrf(request.url.path, request.method):
        return await call_next(request)

    csrf_cookie = request.cookies.get(CSRF_COOKIE)
    csrf_header = request.headers.get("X-CSRF-Token")
    session_token = request.cookies.get(settings.session_cookie_name)
    signup_token = request.cookies.get(SIGNUP_COOKIE)

    context = _pick_context(request.url.path, session_token, signup_token)

    if context:
        context_token, context_name = context
        if not csrf_cookie or not csrf_header:
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_TOKEN_MISSING",
                        "message": "La solicitud requiere un token CSRF.",
                        "retryable": False,
                    }
                },
            )

        if not _validate_csrf_token(context_token, csrf_cookie, context_name):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_TOKEN_INVALID",
                        "message": "El token CSRF no es válido.",
                        "retryable": False,
                    }
                },
            )
        if not hmac.compare_digest(csrf_cookie, csrf_header):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "CSRF_TOKEN_MISMATCH",
                        "message": "El token CSRF no coincide.",
                        "retryable": False,
                    }
                },
            )

    response = await call_next(request)
    return response
