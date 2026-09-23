from __future__ import annotations

import sys
if sys.platform == "win32":
    import asyncio
    import selectors
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
    except Exception:
        pass

import logging
import secrets
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.assets.routes import router as asset_router
from app.business.routes import router as business_router
from app.capabilities.routes import router as capabilities_router
from app.conversations.routes import router as conversation_router
from app.core.config import settings
from app.core.cookies import CSRF_COOKIE, SIGNUP_COOKIE, set_csrf_cookie
from app.core.ephemeral_store import get_ephemeral_store
from app.core.errors import AppError, app_error_handler
from app.core.hosts import trusted_host_middleware
from app.core.infrastructure import get_infrastructure_capabilities
from app.core.rate_limit import LocalRateLimiter, RateLimiter, RedisRateLimiter
from app.db.session import get_session_factory
from app.identity.routes import router as identity_router
from app.images.routes import router as images_router
from app.operations.monitoring import get_error_tracker, metrics
from app.operations.routes import router as operations_router
from app.projects.routes import router as project_router
from app.social.routes import router as social_router
from app.templates.routes import router as template_router
from app.trends.routes import router as trends_router
from app.videos.routes import router as videos_router

logger = logging.getLogger("hitrendy.http")
logger.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings.validate_runtime_configuration()
    if settings.redis_required:
        await get_ephemeral_store().ensure_available()
    if settings.is_demo:
        await _seed_templates()
    yield


async def _seed_templates() -> None:
    from app.templates.repository import seed_templates

    factory = get_session_factory()
    async with factory() as session:
        await seed_templates(session)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

_CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_CORS_HEADERS = [
    "Content-Type",
    "Authorization",
    "X-CSRF-Token",
    "X-Request-Id",
    "Idempotency-Key",
    # Carried by the public deletion status screen, which has no session.
    "X-Deletion-Status-Token",
]

app.add_exception_handler(AppError, app_error_handler)

_RATE_LIMITED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/signup/start",
    "/api/v1/auth/signup/complete",
    "/api/v1/auth/google/start",
    "/api/v1/auth/password-reset/request",
    "/api/v1/auth/password-reset/confirm",
}
_local_rate_limiter = LocalRateLimiter()
_rate_windows = _local_rate_limiter.windows
_rate_limiter: RateLimiter | None = None
_rate_limiter_url: str | None = None


def _requires_rate_limit(path: str) -> bool:
    return (
        path in _RATE_LIMITED_PATHS
        or path.endswith("/messages")
        or path.endswith("/advisor")
        or path.endswith("/variations")
        or path.endswith("/analyses")
        or path.endswith("/feedback")
        or path.endswith("/abuse/reports")
        or path.endswith("/auth/account/deletion-status")
        # Starting an OAuth handshake writes to the shared state store, so it is
        # limited like the other handshake starts above.
        or path.endswith("/authorize")
    )


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter, _rate_limiter_url
    if settings.redis_provider != "redis" or not settings.redis_url:
        return _local_rate_limiter
    if _rate_limiter is None or _rate_limiter_url != settings.redis_url:
        _rate_limiter = RedisRateLimiter.from_url(settings.redis_url)
        _rate_limiter_url = settings.redis_url
    return _rate_limiter


def _record_request(request: Request, request_id: str, status_code: int, started: float) -> None:
    logger.info(
        "http_request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": round((monotonic() - started) * 1000, 2),
        },
    )
    metrics.record_request(status_code=status_code, duration_ms=(monotonic() - started) * 1000)


async def trusted_host_handler(request: Request, call_next):
    return await trusted_host_middleware(request, call_next)


async def request_controls(request: Request, call_next):
    request_id = getattr(request.state, "request_id", request.headers.get("X-Request-Id") or uuid4().hex)
    content_length = request.headers.get("content-length")
    if _requires_rate_limit(request.url.path):
        key = f"hitrendy:rate-limit:{request.client.host if request.client else 'unknown'}:{request.url.path}"
        if not await get_rate_limiter().allow(
            key=key,
            limit=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        ):
            limited_response = JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Demasiadas solicitudes. Inténtalo nuevamente en un momento.",
                        "retryable": True,
                    }
                },
                headers={
                    "X-Request-Id": request_id,
                    "Retry-After": str(settings.rate_limit_window_seconds),
                },
            )
            return limited_response
    if content_length:
        try:
            requested_bytes = int(content_length)
        except ValueError:
            invalid_length_response = JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_CONTENT_LENGTH",
                        "message": "El tamaño de la solicitud no es válido.",
                        "retryable": False,
                    }
                },
                headers={"X-Request-Id": request_id},
            )
            return invalid_length_response
        if requested_bytes > settings.max_request_body_bytes:
            oversized_response = JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "La solicitud supera el tamaño permitido.",
                        "retryable": False,
                    }
                },
                headers={"X-Request-Id": request_id},
            )
            return oversized_response
    response = await call_next(request)
    return response


async def security_headers(request: Request, call_next):
    started = monotonic()
    request_id = request.headers.get("X-Request-Id") or uuid4().hex
    request.state.request_id = request_id
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": round((monotonic() - started) * 1000, 2),
            },
        )
        get_error_tracker().capture(
            request_id=request_id,
            path=request.url.path,
            error_type="internal_error",
        )
        response = JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Ocurrió un error interno.",
                    "retryable": True,
                }
            },
        )
    response.headers["X-Request-Id"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), geolocation=(), microphone=()"
    )
    if request.url.path.endswith("/auth/account/deletion-status"):
        # Also covers the rejection paths, which never reach the route handler.
        response.headers["Cache-Control"] = "no-store"
    if settings.is_production_like and request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            f"max-age={settings.hsts_max_age_seconds}"
            f"{'; includeSubDomains' if settings.hsts_include_subdomains else ''}"
        )
    _record_request(request, request_id, response.status_code, started)
    return response


async def csrf_handler(request: Request, call_next):
    if not settings.csrf_enabled:
        return await call_next(request)

    from app.core.csrf import (
        _generate_csrf_token,
        _pick_context,
        should_validate_csrf,
    )

    path = request.url.path
    method = request.method
    session_token = request.cookies.get(settings.session_cookie_name)
    signup_token = request.cookies.get(SIGNUP_COOKIE)

    if not should_validate_csrf(path, method):
        response = await call_next(request)
        if method in {"GET", "HEAD"} and not request.cookies.get(CSRF_COOKIE):
            context = _pick_context(path, session_token, signup_token)
            if context:
                context_token, context_name = context
                csrf_token = _generate_csrf_token(context_token, context_name)
                set_csrf_cookie(response, csrf_token)
        return response

    from app.core.csrf import csrf_middleware

    return await csrf_middleware(request, call_next)


class RequestBodyLimitMiddleware:
    """Enforce the configured byte limit while the ASGI body stream is consumed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = next(
            (value for key, value in scope.get("headers", []) if key == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > settings.max_request_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._invalid_length(scope, receive, send)
                return

        received_bytes = 0
        rejected = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes, rejected
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > settings.max_request_body_bytes:
                    rejected = True
                    if not response_started:
                        await self._reject(scope, receive, send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if rejected:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        await self.app(scope, limited_receive, guarded_send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            status_code=413,
            content={"error": {"code": "REQUEST_TOO_LARGE", "message": "La solicitud supera el tamaño permitido.", "retryable": False}},
        )(scope, receive, send)

    @staticmethod
    async def _invalid_length(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            status_code=400,
            content={"error": {"code": "INVALID_CONTENT_LENGTH", "message": "El tamaño de la solicitud no es válido.", "retryable": False}},
        )(scope, receive, send)
app.add_middleware(BaseHTTPMiddleware, dispatch=trusted_host_handler)
app.add_middleware(BaseHTTPMiddleware, dispatch=request_controls)
app.add_middleware(BaseHTTPMiddleware, dispatch=csrf_handler)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=True,
    allow_methods=_CORS_METHODS,
    allow_headers=_CORS_HEADERS,
)


app.include_router(capabilities_router, prefix=settings.api_prefix)
app.include_router(business_router, prefix=settings.api_prefix)
app.include_router(identity_router, prefix=settings.api_prefix)
app.include_router(conversation_router, prefix=settings.api_prefix)
app.include_router(project_router, prefix=settings.api_prefix)
app.include_router(asset_router, prefix=settings.api_prefix)
app.include_router(template_router, prefix=settings.api_prefix)
app.include_router(trends_router, prefix=settings.api_prefix)
app.include_router(images_router, prefix=settings.api_prefix)
app.include_router(videos_router, prefix=settings.api_prefix)
app.include_router(social_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)


@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False, response_model=None)
@app.get("/health/metrics", response_class=PlainTextResponse, include_in_schema=False, response_model=None)
async def metrics_endpoint(request: Request) -> Response:
    """Expose low-cardinality process metrics for a deployment monitor."""

    if not settings.metrics_enabled:
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    if settings.metrics_auth_token:
        provided = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.metrics_auth_token}"
        if not secrets.compare_digest(provided, expected):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
    return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", response_model=None)
async def ready() -> dict[str, object] | JSONResponse:
    try:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.exception("database_health_check_failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": {"database": "unavailable", "detail": str(exc)},
            },
        )
    capabilities = await get_infrastructure_capabilities()
    if settings.redis_required and capabilities["redis"] != "available":
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "checks": {"database": "ok", **capabilities},
            },
        )
    return {"status": "ok", "checks": {"database": "ok", **capabilities}}
