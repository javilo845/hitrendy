"""Opt-in smoke that spends exactly one real image generation.

This file is excluded from every default and CI run. It only executes when an
operator sets ``RUN_REAL_IMAGES_SMOKE=1`` together with a real OpenRouter key
and an image model that is on the operator allow-list, and it is additionally
gated behind the ``real_images`` marker so ``-m "not real_images"`` deselects it
even if the environment happens to be configured.

Nothing here prints the key, the request headers or the provider body: the
assertions are on the decoded image only.
"""

from __future__ import annotations

import os

import pytest

from app.assets.validation import validate_image_bytes
from app.providers.images import (
    ASPECT_RATIOS,
    ImageGenerationRequest,
    OpenRouterImageGenerationProvider,
)


def _smoke_skip_reason() -> str | None:
    if os.environ.get("RUN_REAL_IMAGES_SMOKE", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return "RUN_REAL_IMAGES_SMOKE no está habilitada."
    if os.environ.get("IMAGE_PROVIDER", "").strip().lower() != "openrouter":
        return "IMAGE_PROVIDER debe ser openrouter para el smoke real."
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return "Falta OPENROUTER_API_KEY para el smoke real."
    model = os.environ.get("IMAGE_GENERATION_MODEL", "").strip()
    if not model:
        return "Falta IMAGE_GENERATION_MODEL para el smoke real."
    allowed = {
        item.strip()
        for item in os.environ.get("IMAGE_GENERATION_ALLOWED_MODELS", "").split(",")
        if item.strip()
    }
    if model not in allowed:
        return "IMAGE_GENERATION_MODEL no está en IMAGE_GENERATION_ALLOWED_MODELS."
    return None


pytestmark = pytest.mark.skipif(
    _smoke_skip_reason() is not None,
    reason=_smoke_skip_reason() or "Configuración de smoke real incompleta.",
)


@pytest.mark.real_images
@pytest.mark.asyncio
async def test_openrouter_single_image_smoke() -> None:
    """Exactly one paid image, validated with the same guard as an upload."""

    ratio = "1:1"
    width, height = ASPECT_RATIOS[ratio]
    provider = OpenRouterImageGenerationProvider(
        base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.environ["OPENROUTER_API_KEY"],
        model_name=os.environ["IMAGE_GENERATION_MODEL"],
        timeout_seconds=float(os.environ.get("IMAGE_GENERATION_TIMEOUT_SECONDS", "120")),
        max_retries=0,
    )
    generated = await provider.generate(
        request=ImageGenerationRequest(
            prompt=(
                "Fotografía de producto de una taza de café frío sobre una mesa de "
                "madera, luz natural suave, fondo limpio."
            ),
            aspect_ratio=ratio,
            width=width,
            height=height,
        )
    )
    metadata = validate_image_bytes(generated.content, generated.mime_type)
    assert metadata.width > 0
    assert metadata.height > 0
    assert generated.provider_name == "openrouter"
    # Only counters may survive the provider boundary.
    assert set(generated.usage_metadata) <= {
        "provider",
        "model",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
    }
