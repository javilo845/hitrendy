from __future__ import annotations

from typing import Literal, TypedDict

from app.core.config import settings
from app.core.ephemeral_store import get_ephemeral_store
from app.providers.storage import get_object_storage_provider

CapabilityStatus = Literal["available", "unconfigured", "disabled", "degraded", "error"]


class InfrastructureCapabilities(TypedDict):
    storage: CapabilityStatus
    redis: CapabilityStatus


async def get_infrastructure_capabilities() -> InfrastructureCapabilities:
    """Report safe operational states without exposing provider configuration."""

    storage_status: CapabilityStatus
    if settings.object_storage_provider == "disabled":
        storage_status = "disabled"
    elif (
        settings.object_storage_provider == "supabase"
        and not all(
            [settings.supabase_url, settings.supabase_service_role_key, settings.supabase_storage_bucket]
        )
    ) or (
        settings.object_storage_provider == "s3"
        and not all(
            [
                settings.object_storage_endpoint,
                settings.object_storage_access_key,
                settings.object_storage_secret_key,
                settings.object_storage_bucket,
            ]
        )
    ):
        storage_status = "unconfigured"
    else:
        try:
            await get_object_storage_provider().ensure_available()
            storage_status = "available"
        except Exception:
            storage_status = "error"

    redis_status: CapabilityStatus
    if settings.redis_provider == "disabled":
        redis_status = "disabled"
    elif settings.redis_provider == "memory":
        redis_status = "available"
    elif not settings.redis_url and not (
        settings.upstash_redis_rest_url and settings.upstash_redis_rest_token
    ):
        redis_status = "unconfigured"
    else:
        try:
            await get_ephemeral_store().ensure_available()
            redis_status = "available"
        except Exception:
            redis_status = "error" if settings.redis_required else "degraded"

    return {"storage": storage_status, "redis": redis_status}
