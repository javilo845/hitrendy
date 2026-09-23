from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.errors import AppError
from app.domain.models import (
    BusinessGenerationContext,
    GeneratedSocialPost,
    GenerateSocialPostCommand,
)
from app.services.generate_social_post import GenerateSocialPostService


def _context() -> BusinessGenerationContext:
    return BusinessGenerationContext(
        business_id="biz_001",
        name="Café Central",
        category="gastronomy",
        city="Tegucigalpa",
        country="Honduras",
        primary_product="Café frío",
        target_audience="Estudiantes",
        preferred_platforms=["instagram"],
        primary_objective="sales",
        brand_tones=["friendly"],
        value_proposition="Café cercano",
        forbidden_words=["barato"],
        profile_version=3,
    )


def _artifact() -> dict:
    return {
        "artifact_type": "social_post",
        "platform": "instagram",
        "hook": "Una pausa fría para tu día",
        "caption": "Conoce nuestro café frío preparado para estudiantes.",
        "call_to_action": "Visítanos hoy.",
        "hashtags": ["#CafeFrio"],
        "visual_direction": "Producto claro sobre una mesa luminosa.",
        "format_recommendation": "reel",
        "assumptions": ["Se utilizó el tono amistoso del perfil."],
    }


class ContextRepository:
    async def get_for_generation(
        self, *, workspace_id: str, business_id: str
    ) -> BusinessGenerationContext:
        assert workspace_id == "ws_001"
        assert business_id == "biz_001"
        return _context()


class ArtifactRepository:
    saved: dict | None = None

    async def save_social_post(self, **kwargs: object) -> GeneratedSocialPost:
        self.saved = kwargs
        return kwargs["artifact"]  # type: ignore[return-value]

    async def add_artifact_version(self, **kwargs: object) -> GeneratedSocialPost:
        self.saved = kwargs
        return kwargs["content"]  # type: ignore[return-value]


class RepairingProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self) -> None:
        self.repair_calls = 0

    async def generate_social_post(self, *, request: object) -> dict:
        return {"platform": "instagram"}

    async def repair_social_post(
        self, *, request: object, invalid_output: dict, errors: list[str]
    ) -> dict:
        self.repair_calls += 1
        assert errors
        return _artifact()


class QualityRepairingProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self) -> None:
        self.repair_calls = 0

    async def generate_social_post(self, *, request: object) -> dict:
        artifact = _artifact()
        artifact["caption"] = "Café frío por $99 con resultados garantizados."
        return artifact

    async def repair_social_post(
        self, *, request: object, invalid_output: dict, errors: list[str]
    ) -> dict:
        self.repair_calls += 1
        assert any("precio o descuento" in error or "garantía" in error for error in errors)
        return _artifact()


class UsageRepairingProvider(QualityRepairingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def generate_social_post(self, *, request: object) -> dict:
        self.calls += 1
        payload = await super().generate_social_post(request=request)
        payload["__provider_metadata"] = {
            "requested_model": "openrouter/free",
            "actual_model": "physical/first",
            "prompt_tokens": 3,
            "completion_tokens": 5,
            "total_tokens": 8,
            "reported_cost": Decimal("0.001"),
            "currency": "USD",
            "provider_request_id": "first-request",
        }
        return payload

    async def repair_social_post(
        self, *, request: object, invalid_output: dict, errors: list[str]
    ) -> dict:
        self.calls += 1
        payload = await super().repair_social_post(
            request=request, invalid_output=invalid_output, errors=errors
        )
        payload["__provider_metadata"] = {
            "requested_model": "openrouter/free",
            "actual_model": "physical/second",
            "prompt_tokens": 7,
            "completion_tokens": 11,
            "total_tokens": 18,
            "reported_cost": Decimal("0.002"),
            "currency": "USD",
            "provider_request_id": "second-request",
        }
        return payload


@pytest.mark.asyncio
async def test_generation_rejects_invalid_output_without_persisting_an_artifact() -> None:
    repository = ArtifactRepository()
    provider = RepairingProvider()
    service = GenerateSocialPostService(ContextRepository(), repository, provider)

    with pytest.raises(AppError, match="GENERATION_CONTRACT_INVALID"):
        await service.execute(
            GenerateSocialPostCommand(
                workspace_id="ws_001",
                business_id="biz_001",
                conversation_id="conv_001",
                text="Promociona el café frío",
                platform="instagram",
                objective="sales",
            )
        )

    assert provider.repair_calls == 0
    assert repository.saved is None


@pytest.mark.asyncio
async def test_variation_rejects_invalid_output_without_new_version() -> None:
    repository = ArtifactRepository()
    provider = RepairingProvider()
    service = GenerateSocialPostService(ContextRepository(), repository, provider)

    with pytest.raises(AppError, match="GENERATION_CONTRACT_INVALID"):
        await service.execute_variation(
            command=GenerateSocialPostCommand(
                workspace_id="ws_001",
                business_id="biz_001",
                conversation_id="conv_001",
                text="Hazlo más corto",
            ),
            artifact_id="artifact_001",
            parent_version_id="version_001",
        )

    assert provider.repair_calls == 0
    assert repository.saved is None


@pytest.mark.asyncio
async def test_generation_repairs_unconfirmed_commercial_claims() -> None:
    repository = ArtifactRepository()
    provider = QualityRepairingProvider()
    service = GenerateSocialPostService(ContextRepository(), repository, provider)

    artifact = await service.execute(
        GenerateSocialPostCommand(
            workspace_id="ws_001",
            business_id="biz_001",
            conversation_id="conv_001",
            text="Promociona el café frío",
        )
    )

    assert artifact.caption == _artifact()["caption"]
    assert provider.repair_calls == 1


@pytest.mark.asyncio
async def test_quality_repair_aggregates_all_provider_usage_metadata() -> None:
    repository = ArtifactRepository()
    provider = UsageRepairingProvider()
    service = GenerateSocialPostService(ContextRepository(), repository, provider)

    await service.execute(
        GenerateSocialPostCommand(
            workspace_id="ws_001",
            business_id="biz_001",
            conversation_id="conv_001",
            text="Promociona el café frío",
        )
    )

    assert provider.calls == 2
    assert repository.saved is not None
    assert service.usage_metadata == {
        "requested_model": "openrouter/free",
        "currency": "USD",
        "actual_model": "physical/second",
        "provider_request_id": "second-request",
        "prompt_tokens": 10,
        "completion_tokens": 16,
        "total_tokens": 26,
        "reported_cost": Decimal("0.003"),
    }
