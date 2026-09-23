from __future__ import annotations

import json
from typing import overload

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.models import BrandProfile, Business
from app.conversations.models import (
    ArtifactVersion,
    Conversation,
    GeneratedArtifact,
    Message,
)
from app.core.errors import NotFoundError
from app.domain.models import (
    BusinessGenerationContext,
    GeneratedShortVideoScript,
    GeneratedSocialPost,
)

GeneratedArtifactContent = GeneratedSocialPost | GeneratedShortVideoScript


async def create_conversation(
    db: AsyncSession,
    workspace_id: str,
    business_id: str,
    title: str,
    created_by: str | None = None,
) -> Conversation:
    business_result = await db.execute(
        select(Business.id).where(Business.id == business_id, Business.workspace_id == workspace_id)
    )
    if business_result.scalar_one_or_none() is None:
        raise NotFoundError("Negocio")
    conv = Conversation(
        workspace_id=workspace_id,
        business_id=business_id,
        title=title,
        created_by=created_by,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def get_conversation(
    db: AsyncSession, workspace_id: str, conversation_id: str
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise NotFoundError("Conversación")
    return conv


async def list_conversations(
    db: AsyncSession,
    workspace_id: str,
    business_id: str | None = None,
    status: str = "active",
    search: str | None = None,
) -> list[Conversation]:
    query = select(Conversation).where(
        Conversation.workspace_id == workspace_id,
        Conversation.status == status,
    )
    if business_id:
        query = query.where(Conversation.business_id == business_id)
    if search:
        query = query.where(Conversation.title.ilike(f"%{search}%"))
    query = query.order_by(Conversation.updated_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def add_message(
    db: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
    intent: str | None = None,
    metadata_json: dict | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        intent=intent,
        metadata_json=json.dumps(metadata_json) if metadata_json else None,
    )
    db.add(msg)
    await db.flush()
    return msg


async def get_messages(db: AsyncSession, conversation_id: str) -> list[Message]:
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


class SqlBusinessContextRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_for_generation(
        self, *, workspace_id: str, business_id: str
    ) -> BusinessGenerationContext:
        business = None
        if business_id:
            result = await self._db.execute(
                select(Business).where(
                    Business.id == business_id,
                    Business.workspace_id == workspace_id,
                )
            )
            business = result.scalar_one_or_none()

        if business is None:
            result = await self._db.execute(
                select(Business).where(
                    Business.workspace_id == workspace_id,
                ).order_by(Business.created_at.desc())
            )
            business = result.scalar_one_or_none()

        if business is None:
            return BusinessGenerationContext(
                business_id=business_id or "default_biz",
                name="Mi Negocio",
                category="General",
                city="Local",
                country="Latam",
                primary_product="Productos y Servicios",
                target_audience="Seguidores y clientes potenciales",
                preferred_platforms=["instagram"],
                primary_objective="sales",
                brand_tones=["friendly", "professional"],
                value_proposition="Calidad, cercanía y atención personalizada",
                preferred_words=[],
                forbidden_words=[],
                profile_version=1,
            )

        result = await self._db.execute(
            select(BrandProfile).where(BrandProfile.business_id == business_id)
        )
        brand = result.scalar_one_or_none()

        tones = json.loads(brand.voice_tones) if brand else ["friendly"]
        preferred = json.loads(brand.preferred_words) if brand else []
        forbidden = json.loads(brand.forbidden_words) if brand else []
        value_prop = brand.value_proposition if brand else ""
        profile_version = brand.version if brand else 1

        return BusinessGenerationContext(
            business_id=business.id,
            name=business.name,
            category=business.category,
            city=business.city,
            country=business.country,
            primary_product=business.primary_product,
            target_audience=business.target_audience,
            preferred_platforms=json.loads(business.preferred_platforms),
            primary_objective=business.primary_objective,
            brand_tones=tones,
            value_proposition=value_prop,
            preferred_words=preferred,
            forbidden_words=forbidden,
            profile_version=profile_version,
        )


class SqlArtifactRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

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
    ) -> GeneratedSocialPost:
        await self._save_artifact(
            conversation_id=conversation_id,
            profile_version=profile_version,
            objective=objective,
            provider_name=provider_name,
            model_name=model_name,
            prompt_version=prompt_version,
            artifact=artifact,
        )
        return artifact

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
    ) -> GeneratedShortVideoScript:
        await self._save_artifact(
            conversation_id=conversation_id,
            profile_version=profile_version,
            objective=objective,
            provider_name=provider_name,
            model_name=model_name,
            prompt_version=prompt_version,
            artifact=artifact,
        )
        return artifact

    async def _save_artifact(
        self,
        *,
        conversation_id: str,
        profile_version: int,
        objective: str,
        provider_name: str,
        model_name: str,
        prompt_version: str,
        artifact: GeneratedArtifactContent,
    ) -> GeneratedArtifactContent:
        artifact_record = GeneratedArtifact(
            conversation_id=conversation_id,
            artifact_type=artifact.artifact_type,
            platform=artifact.platform,
            objective=objective,
            model_provider=provider_name,
            model_name=model_name,
            prompt_version=prompt_version,
            business_profile_version=profile_version,
        )
        self._db.add(artifact_record)
        await self._db.flush()

        content = artifact.model_dump()
        version = ArtifactVersion(
            artifact_id=artifact_record.id,
            version_number=1,
            content_json=json.dumps(content),
            user_edited=False,
        )
        self._db.add(version)
        await self._db.flush()

        artifact_record.active_version_id = version.id
        await self._db.flush()
        return artifact

    @overload
    async def add_artifact_version(
        self,
        *,
        artifact_id: str,
        content: GeneratedSocialPost,
        user_edited: bool = False,
        parent_version_id: str | None = None,
    ) -> GeneratedSocialPost: ...

    @overload
    async def add_artifact_version(
        self,
        *,
        artifact_id: str,
        content: GeneratedShortVideoScript,
        user_edited: bool = False,
        parent_version_id: str | None = None,
    ) -> GeneratedShortVideoScript: ...

    async def add_artifact_version(
        self,
        *,
        artifact_id: str,
        content: GeneratedArtifactContent,
        user_edited: bool = False,
        parent_version_id: str | None = None,
    ) -> GeneratedArtifactContent:
        result = await self._db.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == artifact_id)
            .order_by(ArtifactVersion.version_number.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        next_version = (latest.version_number + 1) if latest else 1

        content_data = content.model_dump()
        version = ArtifactVersion(
            artifact_id=artifact_id,
            version_number=next_version,
            content_json=json.dumps(content_data),
            user_edited=user_edited,
            parent_version_id=parent_version_id,
        )
        self._db.add(version)
        await self._db.flush()

        art_result = await self._db.execute(
            select(GeneratedArtifact).where(GeneratedArtifact.id == artifact_id)
        )
        artifact_record = art_result.scalar_one_or_none()
        if artifact_record:
            artifact_record.active_version_id = version.id
            await self._db.flush()

        return content
