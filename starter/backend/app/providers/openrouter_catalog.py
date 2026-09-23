from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, Field

from app.core.ephemeral_store import EphemeralStore, get_ephemeral_store


class OpenRouterModel(BaseModel):
    """Internal, defensive representation of the OpenRouter model catalogue."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    context_length: int | None = Field(default=None, ge=1)
    prompt_price: Decimal | None = Field(default=None, ge=0)
    completion_price: Decimal | None = Field(default=None, ge=0)
    supported_parameters: list[str] = Field(default_factory=list, max_length=64)
    structured_output_support: bool = False


CatalogueFetcher = Callable[[], Awaitable[list[object]]]


class OpenRouterModelCatalog:
    """Optional cached catalogue. Generation never depends on catalogue availability."""

    cache_key = "openrouter:model-catalog:v1"

    def __init__(
        self,
        *,
        ttl_seconds: int,
        store: EphemeralStore | None = None,
        fetcher: CatalogueFetcher,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._store = store or get_ephemeral_store()
        self._fetcher = fetcher

    async def list_models(self) -> list[OpenRouterModel]:
        cached = await self._load_cache()
        if cached is not None:
            return cached
        try:
            remote_models = await self._fetcher()
            models = [parsed for item in remote_models if (parsed := _parse_model(item)) is not None]
        except (ValueError, TypeError):
            # Catalogue availability is observability, never a generation gate.
            return []
        await self._save_cache(models)
        return models

    async def _load_cache(self) -> list[OpenRouterModel] | None:
        try:
            raw = await self._store.get(key=self.cache_key)
        except Exception:
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            if not isinstance(payload, list):
                return None
            return [OpenRouterModel.model_validate(item) for item in payload]
        except (ValueError, TypeError):
            return None

    async def _save_cache(self, models: list[OpenRouterModel]) -> None:
        try:
            await self._store.set(
                key=self.cache_key,
                value=json.dumps([model.model_dump(mode="json") for model in models]),
                ttl_seconds=self._ttl_seconds,
            )
        except Exception:
            return None

def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result >= 0 else None


def _parse_model(item: object) -> OpenRouterModel | None:
    if not isinstance(item, dict):
        return None
    model_id = item.get("id")
    name = item.get("name")
    if not isinstance(model_id, str) or not model_id.strip() or not isinstance(name, str) or not name.strip():
        return None
    pricing = item.get("pricing") if isinstance(item.get("pricing"), dict) else {}
    parameters = item.get("supported_parameters")
    supported = [value for value in parameters if isinstance(value, str)][:64] if isinstance(parameters, list) else []
    context_length = item.get("context_length")
    return OpenRouterModel(
        model_id=model_id,
        name=name,
        context_length=context_length if isinstance(context_length, int) and context_length > 0 else None,
        prompt_price=_as_decimal(pricing.get("prompt")),
        completion_price=_as_decimal(pricing.get("completion")),
        supported_parameters=supported,
        structured_output_support=("response_format" in supported or "structured_outputs" in supported),
    )
