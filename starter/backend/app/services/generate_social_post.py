from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from app.core.errors import AppError
from app.domain.models import (
    BusinessGenerationContext,
    GeneratedSocialPost,
    GenerateSocialPostCommand,
)
from app.generation.contracts import SocialPostModelRequest
from app.generation.evaluation import SocialPostEvaluator
from app.generation.prompt_registry import get_social_copy_prompt
from app.providers.content import ContentModelProvider
from app.services.ai_usage import combine_usage_metadata


class BusinessContextRepository(Protocol):
    async def get_for_generation(
        self, *, workspace_id: str, business_id: str
    ) -> BusinessGenerationContext: ...


class ArtifactRepository(Protocol):
    async def save_social_post(
        self,
        *,
        workspace_id: str,
        conversation_id: str,
        profile_version: int,
        objective: str,
        provider_name: str,
        model_name: str,
        prompt_version: str,
        artifact: GeneratedSocialPost,
    ) -> GeneratedSocialPost: ...

    async def add_artifact_version(
        self,
        *,
        artifact_id: str,
        content: GeneratedSocialPost,
        user_edited: bool = False,
        parent_version_id: str | None = None,
    ) -> GeneratedSocialPost: ...


class GenerateSocialPostService:
    def __init__(
        self,
        business_repository: BusinessContextRepository,
        artifact_repository: ArtifactRepository,
        provider: ContentModelProvider,
        evaluator: SocialPostEvaluator | None = None,
    ) -> None:
        self._business_repository = business_repository
        self._artifact_repository = artifact_repository
        self._provider = provider
        self._evaluator = evaluator or SocialPostEvaluator()
        self.usage_metadata: dict[str, object] | None = None

    async def execute(self, command: GenerateSocialPostCommand) -> GeneratedSocialPost:
        artifact, context, request = await self._generate(command)
        return await self._artifact_repository.save_social_post(
            workspace_id=command.workspace_id,
            conversation_id=command.conversation_id,
            profile_version=context.profile_version,
            objective=request.objective,
            provider_name=self._provider.provider_name,
            model_name=self._provider.model_name,
            prompt_version=request.prompt_version,
            artifact=artifact,
        )

    async def execute_variation(
        self,
        *,
        command: GenerateSocialPostCommand,
        artifact_id: str,
        parent_version_id: str | None,
    ) -> GeneratedSocialPost:
        artifact, _, _ = await self._generate(command)
        return await self._artifact_repository.add_artifact_version(
            artifact_id=artifact_id,
            content=artifact,
            parent_version_id=parent_version_id,
        )

    async def _generate(
        self, command: GenerateSocialPostCommand
    ) -> tuple[GeneratedSocialPost, BusinessGenerationContext, SocialPostModelRequest]:
        context = await self._business_repository.get_for_generation(
            workspace_id=command.workspace_id,
            business_id=command.business_id,
        )
        _, prompt_version = get_social_copy_prompt()
        request = SocialPostModelRequest.from_command(
            context=context, command=command, prompt_version=prompt_version
        )
        raw = await self._provider.generate_social_post(request=request)
        self.usage_metadata = raw.pop("__provider_metadata", None)
        try:
            artifact = GeneratedSocialPost.model_validate(raw)
        except ValidationError as exc:
            raise AppError(
                "GENERATION_CONTRACT_INVALID",
                "No pudimos preparar una propuesta válida. Inténtalo nuevamente.",
                status_code=502,
                retryable=True,
            ) from exc
        evaluation = self._evaluator.evaluate(artifact, request)
        if not evaluation.accepted:
            raw = await self._provider.repair_social_post(
                request=request,
                invalid_output=artifact.model_dump(),
                errors=list(evaluation.issues),
            )
            repair_metadata = raw.pop("__provider_metadata", None)
            self.usage_metadata = combine_usage_metadata(
                self.usage_metadata,
                repair_metadata if isinstance(repair_metadata, dict) else None,
            )
            try:
                artifact = GeneratedSocialPost.model_validate(raw)
            except ValidationError as repair_error:
                raise AppError(
                    "GENERATION_CONTRACT_INVALID",
                    "No pudimos preparar una propuesta válida. Inténtalo nuevamente.",
                    status_code=502,
                    retryable=True,
                ) from repair_error
            final_evaluation = self._evaluator.evaluate(artifact, request)
            if not final_evaluation.accepted:
                raise AppError(
                    "GENERATION_CONTRACT_INVALID",
                    "No pudimos preparar una propuesta válida. Inténtalo nuevamente.",
                    status_code=502,
                    retryable=True,
                )
        return artifact, context, request
