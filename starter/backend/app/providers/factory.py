from __future__ import annotations

from app.core.capabilities import QualityLevel
from app.core.config import settings
from app.core.errors import AppError
from app.providers.content import (
    ContentModelProvider,
    DemoContentModelProvider,
    OpenAICompatibleContentModelProvider,
)
from app.providers.images import (
    DemoImageGenerationProvider,
    ImageGenerationProvider,
    OpenAIImageGenerationProvider,
    OpenRouterImageGenerationProvider,
    ReplicateImageGenerationProvider,
)
from app.providers.openrouter_catalog import OpenRouterModelCatalog
from app.providers.video import (
    DemoVideoGenerationProvider,
    OpenAIVideoGenerationProvider,
    VideoGenerationProvider,
)
from app.providers.vision import (
    DemoVisionReviewProvider,
    OpenAICompatibleVisionReviewProvider,
    VisionReviewProvider,
)


def get_content_provider(
    *, quality_level: QualityLevel = QualityLevel.FAST
) -> ContentModelProvider:
    if settings.ai_provider == "demo":
        if settings.app_env == "production":
            raise AppError(
                "GENERATION_PROVIDER_UNAVAILABLE",
                "La configuración del proveedor de contenido no está disponible.",
                status_code=503,
                retryable=False,
            )
        return DemoContentModelProvider()
    if settings.ai_provider == "openai-compatible":
        if not settings.ai_base_url or not settings.ai_api_key:
            raise AppError(
                "GENERATION_PROVIDER_UNAVAILABLE",
                "La configuración del proveedor de contenido no está disponible.",
                status_code=503,
                retryable=False,
            )
        return OpenAICompatibleContentModelProvider(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model_name=settings.ai_model,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
            retry_base_seconds=settings.ai_retry_base_seconds,
            http_referer=settings.ai_http_referer,
            app_title=settings.ai_app_title,
            # The domain contract forbids extra keys and constrains every field,
            # which plain JSON mode cannot guarantee: the model free-forms a shape
            # that fails validation and the request dies as GENERATION_CONTRACT_INVALID.
            # Schema-constrained decoding makes the provider produce the contract.
            structured_output=True,
        )
    if settings.ai_provider == "openrouter":
        if not settings.openrouter_api_key or not settings.openrouter_fast_model:
            raise AppError(
                "GENERATION_PROVIDER_UNAVAILABLE",
                "La configuración del proveedor de contenido no está disponible.",
                status_code=503,
                retryable=False,
            )
        # Do not trust a mutated Settings instance: fast is the only route
        # deliberately guaranteed free in this wave.
        if settings.openrouter_fast_model != "openrouter/free":
            raise AppError(
                "CAPABILITY_UNAVAILABLE",
                "El modelo rápido de OpenRouter debe ser openrouter/free.",
                status_code=503,
                retryable=False,
            )
        model_by_quality = {
            QualityLevel.FAST: settings.openrouter_fast_model,
            QualityLevel.BALANCED: settings.openrouter_balanced_model,
            QualityLevel.QUALITY: settings.openrouter_quality_model,
        }
        model_name = model_by_quality[quality_level]
        if not model_name:
            raise AppError(
                "CAPABILITY_UNAVAILABLE",
                "El nivel de calidad solicitado no está configurado.",
                status_code=503,
                retryable=False,
            )
        return OpenAICompatibleContentModelProvider(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model_name=model_name,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
            retry_base_seconds=settings.ai_retry_base_seconds,
            http_referer=settings.ai_http_referer,
            app_title=settings.ai_app_title,
            provider_name="openrouter",
            structured_output=True,
        )
    raise AppError(
        "GENERATION_PROVIDER_UNAVAILABLE",
        "El proveedor de contenido configurado no está disponible.",
        status_code=503,
        retryable=False,
    )


def get_openrouter_model_catalog() -> OpenRouterModelCatalog:
    """Build the optional cache around the existing OpenAI-compatible adapter."""
    provider = get_content_provider(quality_level=QualityLevel.FAST)
    if settings.ai_provider != "openrouter" or not isinstance(
        provider, OpenAICompatibleContentModelProvider
    ):
        raise AppError(
            "CAPABILITY_UNAVAILABLE",
            "El catálogo OpenRouter no está configurado.",
            status_code=503,
            retryable=False,
        )
    return OpenRouterModelCatalog(
        ttl_seconds=settings.openrouter_catalog_ttl_seconds,
        fetcher=provider.fetch_model_catalog,
    )


def get_image_generation_provider(
    *, provider: str | None = None, model: str | None = None
) -> ImageGenerationProvider:
    """Build the image provider, optionally for a route persisted earlier.

    With no arguments this answers "what would we run right now", which is what
    a confirmation records on the job. A worker instead passes the route the job
    stored, so a configuration change between confirmation and execution can
    never silently move the spend to another model.

    Persisted values are re-authorized, never trusted: the provider must still
    be a supported one and the model must still be in the operator allow-list.
    A route that is no longer authorized raises here -- before the provider is
    reached -- so the caller can fail the job and return its reservation.
    """

    if not settings.image_generation_enabled:
        raise AppError(
            "CAPABILITY_UNAVAILABLE",
            "La generación de imágenes no está disponible.",
            status_code=503,
            retryable=False,
        )
    selected = (provider or settings.image_provider).strip().lower()
    if selected == "demo":
        if settings.app_env not in {"development", "test"}:
            raise AppError(
                "IMAGE_PROVIDER_UNAVAILABLE",
                "La generación de imágenes no está disponible.",
                status_code=503,
                retryable=False,
            )
        if model is not None and model != DemoImageGenerationProvider.model_name:
            raise AppError(
                "IMAGE_PROVIDER_UNAVAILABLE",
                "La generación de imágenes no está disponible.",
                status_code=503,
                retryable=False,
            )
        return DemoImageGenerationProvider()
    if selected == "openrouter":
        model_name = model if model is not None else settings.image_generation_model
        if (
            not settings.openrouter_api_key
            or not model_name
            or model_name not in settings.image_generation_allowed_models
        ):
            raise AppError(
                "IMAGE_PROVIDER_UNAVAILABLE",
                "La generación de imágenes no está configurada.",
                status_code=503,
                retryable=False,
            )
        return OpenRouterImageGenerationProvider(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model_name=model_name,
            timeout_seconds=settings.image_generation_timeout_seconds,
        )
    if selected == "openai":
        model_name = model if model is not None else settings.image_generation_model
        if (
            not settings.openai_api_key
            or not model_name
            or model_name not in settings.image_generation_allowed_models
        ):
            raise AppError(
                "IMAGE_PROVIDER_UNAVAILABLE",
                "La generación de imágenes no está configurada.",
                status_code=503,
                retryable=False,
            )
        return OpenAIImageGenerationProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model_name=model_name,
            timeout_seconds=settings.image_generation_timeout_seconds,
        )
    if selected == "replicate":
        model_name = model if model is not None else settings.image_generation_model
        if (
            not settings.replicate_api_key
            or not model_name
            or model_name not in settings.image_generation_allowed_models
        ):
            raise AppError(
                "IMAGE_PROVIDER_UNAVAILABLE",
                "La generación de imágenes no está configurada.",
                status_code=503,
                retryable=False,
            )
        return ReplicateImageGenerationProvider(
            api_token=settings.replicate_api_key,
            model_name=model_name,
            timeout_seconds=settings.image_generation_timeout_seconds,
        )
    raise AppError(
        "IMAGE_PROVIDER_UNAVAILABLE",
        "El proveedor de imágenes configurado no está disponible.",
        status_code=503,
        retryable=False,
    )


def get_video_generation_provider() -> VideoGenerationProvider:
    """Build the configured asynchronous video provider."""

    if settings.video_provider == "demo":
        return DemoVideoGenerationProvider()
    if settings.video_provider == "openai":
        if (
            not settings.openai_api_key
            or not settings.video_generation_model
            or settings.video_generation_model not in settings.video_generation_allowed_models
            or not set(settings.video_generation_allowed_durations).issubset({16, 20})
        ):
            raise AppError(
                "VIDEO_PROVIDER_UNAVAILABLE",
                "La generación de video no está configurada.",
                status_code=503,
                retryable=False,
            )
        return OpenAIVideoGenerationProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model_name=settings.video_generation_model,
            timeout_seconds=settings.video_generation_timeout_seconds,
        )
    raise RuntimeError("VIDEO_PROVIDER no es compatible.")


def get_vision_provider() -> VisionReviewProvider:
    """Build the visual-review provider without coupling it to asset storage."""

    if settings.vision_provider == "demo":
        return DemoVisionReviewProvider()
    if settings.vision_provider == "openai-compatible":
        if not settings.vision_base_url or not settings.vision_api_key:
            raise AppError(
                "ANALYSIS_PROVIDER_UNAVAILABLE",
                "La configuración del análisis visual no está disponible.",
                status_code=503,
                retryable=False,
            )
        return OpenAICompatibleVisionReviewProvider(
            base_url=settings.vision_base_url,
            api_key=settings.vision_api_key,
            model_name=settings.vision_model,
            timeout_seconds=settings.ai_timeout_seconds,
        )
    raise AppError(
        "ANALYSIS_PROVIDER_UNAVAILABLE",
        "El proveedor de análisis visual configurado no está disponible.",
        status_code=503,
        retryable=False,
    )
