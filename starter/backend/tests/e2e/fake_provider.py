from __future__ import annotations

import asyncio

from app.core.errors import AppError
from app.generation.contracts import ShortVideoScriptModelRequest, SocialPostModelRequest


class DeterministicE2EProvider:
    """Offline provider used only by the PostgreSQL HTTP tests."""

    provider_name = "e2e-fake"
    model_name = "e2e-fake-v1"

    def __init__(self) -> None:
        self.calls = 0
        self.last_social_request: SocialPostModelRequest | None = None
        self.transient_failures = 0
        self.permanent_failure = False
        self.delay_seconds = 0.0

    async def generate_social_post(self, *, request: SocialPostModelRequest) -> dict:
        self.calls += 1
        self.last_social_request = request
        await self._before_response()
        return {
            "artifact_type": "social_post",
            "platform": request.platform,
            "hook": f"E2E: {request.business.primary_product}",
            "caption": f"Contenido E2E para {request.business.name}.",
            "call_to_action": "Escríbenos para conocer más.",
            "hashtags": ["#E2E", "#HiTrendy"],
            "visual_direction": "Brief visual 4:5: producto centrado, estilo limpio, texto sugerido y guía para Canva.",
            "format_recommendation": "static_post",
            "assumptions": ["Provider determinista de pruebas."],
        }

    async def repair_social_post(
        self,
        *,
        request: SocialPostModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict:
        return await self.generate_social_post(request=request)

    async def generate_short_video_script(self, *, request: ShortVideoScriptModelRequest) -> dict:
        self.calls += 1
        await self._before_response()
        return {
            "artifact_type": "short_video_script",
            "platform": request.platform,
            "hook": f"E2E: {request.business.primary_product}",
            "duration_seconds": 10,
            "scenes": [
                {
                    "order": 1,
                    "duration_seconds": 5,
                    "visual": "Producto en primer plano.",
                    "on_screen_text": "Conócelo hoy",
                    "voiceover": "Una propuesta pensada para tu negocio.",
                },
                {
                    "order": 2,
                    "duration_seconds": 5,
                    "visual": "Cierre con llamada a la acción.",
                    "on_screen_text": "Escríbenos",
                    "voiceover": "Escríbenos para conocer más.",
                },
            ],
            "call_to_action": "Escríbenos para conocer más.",
            "caption": f"Video E2E para {request.business.name}.",
            "assumptions": ["Provider determinista de pruebas."],
        }

    async def repair_short_video_script(
        self,
        *,
        request: ShortVideoScriptModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict:
        return await self.generate_short_video_script(request=request)

    async def _before_response(self) -> None:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.permanent_failure:
            raise AppError(
                "E2E_PROVIDER_FAILURE",
                "El provider de pruebas falló de forma permanente.",
                status_code=502,
                retryable=False,
            )
        if self.transient_failures:
            self.transient_failures -= 1
            raise AppError(
                "E2E_PROVIDER_TEMPORARY_FAILURE",
                "El provider de pruebas falló temporalmente.",
                status_code=503,
                retryable=True,
            )
