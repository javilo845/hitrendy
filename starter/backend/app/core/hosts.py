from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


def get_public_host(request: Request) -> str:
    host = request.headers.get("Host") or "localhost"
    return host.split(":")[0].strip().lower()


async def trusted_host_middleware(request: Request, call_next):
    path = request.url.path
    if path in {"/health/live", "/health/ready"}:
        return await call_next(request)

    from app.core.config import settings

    allowed = settings.allowed_hosts
    if not allowed:
        return await call_next(request)

    host = get_public_host(request)
    if host not in allowed:
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_HOST",
                    "message": "Host no permitido.",
                    "retryable": False,
                }
            },
        )

    response = await call_next(request)
    return response
