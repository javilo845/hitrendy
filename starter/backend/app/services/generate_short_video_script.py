from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from app.core.errors import AppError
from app.domain.models import (
    GeneratedShortVideoScript,
    GenerateShortVideoScriptCommand,
)
from app.generation.contracts import ShortVideoScriptModelRequest
from app.generation.prompt_registry import get_short_video_script_prompt
from app.providers.content import ContentModelProvider
from app.services.ai_usage import combine_usage_metadata
from app.services.generate_social_post import BusinessContextRepository


class VideoArtifactRepository(Protocol):
    async def save_short_video_script(
        self,
        *,
        workspace_id: str,
        conversation_id: str,
        profile_version: int,
        objective: str,
        provider_name: str,
        model_name: str,
        prompt_version: str,
        artifact: GeneratedShortVideoScript,
    ) -> GeneratedShortVideoScript: ...


class GenerateShortVideoScriptService:
    def __init__(
        self,
        business_repository: BusinessContextRepository,
        artifact_repository: VideoArtifactRepository,
        provider: ContentModelProvider,
    ) -> None:
        self._business_repository = business_repository
        self._artifact_repository = artifact_repository
        self._provider = provider
        self.usage_metadata: dict[str, object] | None = None

    async def execute(self, command: GenerateShortVideoScriptCommand) -> GeneratedShortVideoScript:
        context = await self._business_repository.get_for_generation(
            workspace_id=command.workspace_id,
            business_id=command.business_id,
        )
        _, prompt_version = get_short_video_script_prompt()
        request = ShortVideoScriptModelRequest.from_command(
            context=context,
            command=command,
            prompt_version=prompt_version,
        )
        raw = await self._provider.generate_short_video_script(request=request)
        metadata = raw.pop("__provider_metadata", None)
        self.usage_metadata = metadata if isinstance(metadata, dict) else None
        try:
            artifact = GeneratedShortVideoScript.model_validate(raw)
        except ValidationError as exc:
            raw = await self._provider.repair_short_video_script(
                request=request,
                invalid_output=raw if isinstance(raw, dict) else {},
                errors=[error["msg"] for error in exc.errors()],
            )
            repair_metadata = raw.pop("__provider_metadata", None)
            self.usage_metadata = combine_usage_metadata(
                self.usage_metadata,
                repair_metadata if isinstance(repair_metadata, dict) else None,
            )
            try:
                artifact = GeneratedShortVideoScript.model_validate(raw)
            except ValidationError as repair_error:
                raise AppError(
                    "GENERATION_CONTRACT_INVALID",
                    "No pudimos preparar un guion editable. Inténtalo nuevamente.",
                    status_code=502,
                    retryable=True,
                ) from repair_error
        return await self._artifact_repository.save_short_video_script(
            workspace_id=command.workspace_id,
            conversation_id=command.conversation_id,
            profile_version=context.profile_version,
            objective=request.objective,
            provider_name=self._provider.provider_name,
            model_name=self._provider.model_name,
            prompt_version=request.prompt_version,
            artifact=artifact,
        )
