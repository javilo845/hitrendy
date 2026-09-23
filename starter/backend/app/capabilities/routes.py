from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.capabilities import (
    PublicCapabilityResponse,
    get_runtime_capability_registry,
)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])

_registry = get_runtime_capability_registry()


@router.get("", response_model=dict[str, PublicCapabilityResponse])
async def get_capabilities(response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    return await _registry.get_public_snapshot()
