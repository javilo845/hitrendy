from __future__ import annotations

import os

import pytest

from app.domain.models import AdvisorResponse, BusinessGenerationContext
from app.generation.contracts import AdvisorModelRequest
from app.providers.content import OpenAICompatibleContentModelProvider


def _smoke_skip_reason() -> str | None:
    if os.environ.get("RUN_REAL_AI_SMOKE", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        return "RUN_REAL_AI_SMOKE no está habilitada."
    if os.environ.get("AI_PROVIDER", "").strip().lower() != "openrouter":
        return "AI_PROVIDER debe ser openrouter para el smoke real."
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return "Falta OPENROUTER_API_KEY para el smoke real."
    return None


pytestmark = pytest.mark.skipif(
    _smoke_skip_reason() is not None,
    reason=_smoke_skip_reason() or "Configuración de smoke real incompleta.",
)


@pytest.mark.real_ai
@pytest.mark.asyncio
async def test_openrouter_fast_advisor_smoke() -> None:
    """One minimal OpenRouter call, deliberately excluded from normal CI."""
    provider = OpenAICompatibleContentModelProvider(
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        model_name="openrouter/free",
        provider_name="openrouter",
        timeout_seconds=30,
        max_retries=0,
        http_referer=os.environ.get("AI_HTTP_REFERER", ""),
        app_title=os.environ.get("AI_APP_TITLE", "HiTrendy"),
        structured_output=True,
    )
    business = BusinessGenerationContext(
        business_id="real-smoke", name="Café Aurora", category="gastronomy",
        city="Tegucigalpa", country="Honduras", primary_product="café frío",
        target_audience="jóvenes profesionales", preferred_platforms=["instagram"],
        primary_objective="engagement", brand_tones=["friendly"],
        value_proposition="Bebidas preparadas al momento.", forbidden_words=["milagroso"],
    )
    raw = await provider.generate_advice(
        request=AdvisorModelRequest(
            business=business, locale="es", user_request="Da una recomendación breve y accionable."
        )
    )
    metadata = raw.pop("__provider_metadata", {})
    response = AdvisorResponse.model_validate(raw)
    assert response.summary.strip()
    assert metadata.get("requested_model") == "openrouter/free"
    # OpenRouter may omit usage/model metadata for free routing; validate it only if present.
    actual_model = metadata.get("actual_model")
    assert actual_model is None or isinstance(actual_model, str)
    assert metadata.get("total_tokens") is None or isinstance(metadata.get("total_tokens"), int)
