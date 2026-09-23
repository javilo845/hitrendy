from __future__ import annotations

import pytest

from app.domain.models import (
    BusinessGenerationContext,
    GeneratedShortVideoScript,
    GenerateShortVideoScriptCommand,
)
from app.services.generate_short_video_script import GenerateShortVideoScriptService


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
        profile_version=3,
    )


def _artifact() -> dict:
    return {
        "artifact_type": "short_video_script",
        "platform": "instagram",
        "hook": "Una pausa fría para tu día",
        "duration_seconds": 20,
        "scenes": [
            {
                "order": 1,
                "duration_seconds": 5,
                "visual": "Primer plano del café frío.",
                "on_screen_text": "Café frío",
                "voiceover": "Conoce nuestra pausa fría.",
            },
            {
                "order": 2,
                "duration_seconds": 15,
                "visual": "Una persona disfruta el café.",
                "on_screen_text": "Conócelo hoy",
                "voiceover": "Visítanos hoy.",
            },
        ],
        "call_to_action": "Visítanos hoy.",
        "caption": "Conoce nuestro café frío.",
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

    async def save_short_video_script(self, **kwargs: object) -> GeneratedShortVideoScript:
        self.saved = kwargs
        return kwargs["artifact"]  # type: ignore[return-value]


class RepairingProvider:
    provider_name = "test-provider"
    model_name = "test-model"

    def __init__(self) -> None:
        self.repair_calls = 0

    async def generate_short_video_script(self, *, request: object) -> dict:
        return {"artifact_type": "short_video_script"}

    async def repair_short_video_script(
        self, *, request: object, invalid_output: dict, errors: list[str]
    ) -> dict:
        self.repair_calls += 1
        assert errors
        return _artifact()


@pytest.mark.asyncio
async def test_video_script_repairs_invalid_output_and_persists_audit_metadata() -> None:
    repository = ArtifactRepository()
    provider = RepairingProvider()
    service = GenerateShortVideoScriptService(ContextRepository(), repository, provider)

    artifact = await service.execute(
        GenerateShortVideoScriptCommand(
            workspace_id="ws_001",
            business_id="biz_001",
            conversation_id="conv_001",
            text="Crea un guion para el café frío",
            platform="instagram",
            objective="sales",
        )
    )

    assert artifact.duration_seconds == 20
    assert provider.repair_calls == 1
    assert repository.saved is not None
    assert repository.saved["objective"] == "sales"
    assert repository.saved["provider_name"] == "test-provider"
    assert repository.saved["prompt_version"] == "short-video-script@1.0.0"
