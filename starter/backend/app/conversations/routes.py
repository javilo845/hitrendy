from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.analysis_service import analysis_to_dict, analyze_authorized_asset
from app.conversations.idempotency import (
    complete,
    mark_failed,
    payload_fingerprint,
    recover_failed,
    reserve,
)
from app.conversations.models import (
    ArtifactEvent,
    ArtifactFeedback,
    ArtifactVersion,
    Conversation,
    GeneratedArtifact,
    Message,
)
from app.conversations.repository import (
    SqlArtifactRepository,
    SqlBusinessContextRepository,
    add_message,
    create_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)
from app.core.capabilities import Capability, CapabilityRegistry, QualityLevel
from app.core.errors import AppError, NotFoundError, ValidationError_
from app.dependencies import CurrentPrincipal, get_current_principal, get_db, require_workspace
from app.domain.models import (
    GeneratedShortVideoScript,
    GeneratedSocialPost,
    GenerateShortVideoScriptCommand,
    GenerateSocialPostCommand,
    Objective,
    Platform,
    Tone,
    VariationKind,
)
from app.providers.factory import get_content_provider
from app.services.ai_usage import outcome_for_error, record_usage
from app.services.generate_advice import GenerateAdviceService
from app.services.generate_short_video_script import GenerateShortVideoScriptService
from app.services.generate_social_post import GenerateSocialPostService
from app.services.usage_policy import ensure_generation_allowed

router = APIRouter(prefix="/conversations", tags=["conversations"])
SupportedGenerationIntent = Literal[
    "create_social_post", "create_short_video_script", "analyze_visual", "ask_advisor"
]


class CreateConversationRequest(BaseModel):
    business_id: str
    title: str = Field(min_length=1, max_length=240)


class SendMessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    ui_intent: str | None = Field(None, max_length=80)
    platform: Platform | None = None
    tone: Tone | None = None
    objective: Objective | None = None
    quality_level: QualityLevel = QualityLevel.FAST
    locale: Literal["es", "en", "pt"] = "es"
    attachment_ids: list[str] = Field(default_factory=list, max_length=5)


class UpdateConversationRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=240)
    status: Literal["active", "archived"] | None = None


class ArtifactFeedbackRequest(BaseModel):
    rating: Literal["useful", "not_useful"]
    reason: str | None = Field(None, max_length=500)


class ArtifactEventRequest(BaseModel):
    event_type: Literal["copied", "saved"]


@router.post("/artifacts/{artifact_id}/feedback", status_code=201)
async def create_artifact_feedback_endpoint(
    artifact_id: str,
    body: ArtifactFeedbackRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(GeneratedArtifact)
        .join(Conversation, Conversation.id == GeneratedArtifact.conversation_id)
        .where(GeneratedArtifact.id == artifact_id, Conversation.workspace_id == workspace_id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Artículo")
    feedback = ArtifactFeedback(artifact_id=artifact_id, rating=body.rating, reason=body.reason)
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)
    return {"id": feedback.id, "artifact_id": feedback.artifact_id, "rating": feedback.rating}


@router.post("/artifacts/{artifact_id}/events", status_code=201)
async def create_artifact_event_endpoint(
    artifact_id: str,
    body: ArtifactEventRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(GeneratedArtifact)
        .join(Conversation, Conversation.id == GeneratedArtifact.conversation_id)
        .where(GeneratedArtifact.id == artifact_id, Conversation.workspace_id == workspace_id)
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Artículo")
    event = ArtifactEvent(artifact_id=artifact_id, event_type=body.event_type)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {"id": event.id, "artifact_id": event.artifact_id, "event_type": event.event_type}


@router.post("", status_code=201)
async def create_conversation_endpoint(
    body: CreateConversationRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await create_conversation(db, workspace_id, body.business_id, body.title)
    await db.commit()
    return {
        "id": conv.id,
        "workspace_id": conv.workspace_id,
        "business_id": conv.business_id,
        "title": conv.title,
        "status": conv.status,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
    }


@router.get("")
async def list_conversations_endpoint(
    business_id: str | None = None,
    status: Literal["active", "archived"] = "active",
    search: str | None = Query(None, min_length=1, max_length=120),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    convs = await list_conversations(db, workspace_id, business_id, status, search)
    latest_message = (
        select(Message.content)
        .where(Message.conversation_id == Conversation.id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    # Load the compact history card data in one query, rather than one message query per thread.
    history_result = (
        await db.execute(
            select(Conversation.id, latest_message.label("last_message")).where(
                Conversation.id.in_([c.id for c in convs]),
                Conversation.workspace_id == workspace_id,
            )
        )
        if convs
        else None
    )
    last_messages = {row.id: row.last_message for row in history_result} if history_result else {}
    return [
        {
            "id": c.id,
            "title": c.title,
            "business_id": c.business_id,
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "last_message": last_messages.get(c.id),
        }
        for c in convs
    ]


@router.patch("/{conversation_id}")
async def update_conversation_endpoint(
    conversation_id: str,
    body: UpdateConversationRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await get_conversation(db, workspace_id, conversation_id)
    if body.title is not None:
        conversation.title = body.title
    if body.status is not None:
        conversation.status = body.status
    await db.commit()
    await db.refresh(conversation)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "status": conversation.status,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
    }


@router.get("/{conversation_id}")
async def get_conversation_endpoint(
    conversation_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await get_conversation(db, workspace_id, conversation_id)
    msgs = await get_messages(db, conversation_id)
    message_metadata = {
        message.id: json.loads(message.metadata_json) if message.metadata_json else None
        for message in msgs
    }
    artifact_ids = [
        metadata["artifact_id"]
        for metadata in message_metadata.values()
        if metadata and isinstance(metadata.get("artifact_id"), str)
    ]
    artifacts_by_id: dict[str, dict] = {}
    if artifact_ids:
        artifact_result = await db.execute(
            select(GeneratedArtifact.id, ArtifactVersion.content_json)
            .join(ArtifactVersion, ArtifactVersion.id == GeneratedArtifact.active_version_id)
            .where(
                GeneratedArtifact.id.in_(artifact_ids),
                GeneratedArtifact.conversation_id == conversation_id,
            )
        )
        artifacts_by_id = {
            row.id: json.loads(row.content_json) for row in artifact_result if row.content_json
        }
    return {
        "id": conv.id,
        "title": conv.title,
        "business_id": conv.business_id,
        "status": conv.status,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "metadata": message_metadata[m.id],
                "artifact_id": message_metadata[m.id].get("artifact_id")
                if message_metadata[m.id]
                else None,
                "artifact": artifacts_by_id.get(message_metadata[m.id].get("artifact_id"))
                if message_metadata[m.id]
                else None,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
        ],
    }


@router.post("/{conversation_id}/messages")
async def send_message_endpoint(
    conversation_id: str,
    body: SendMessageRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    endpoint = f"/conversations/{conversation_id}/messages"
    conversation = await get_conversation(db, workspace_id, conversation_id)
    if conversation.status != "active":
        raise ValidationError_("Restaura la conversación antes de enviar un mensaje.")
    intent: SupportedGenerationIntent
    text_lower = body.text.lower()
    if body.ui_intent is not None and body.ui_intent not in (
        "create_social_post", "create_short_video_script", "analyze_visual", "ask_advisor"
    ):
        raise ValidationError_("Esta acción todavía no está disponible en el asistente.")

    if body.ui_intent == "analyze_visual":
        intent = "analyze_visual"
    elif body.ui_intent == "create_short_video_script" or (body.ui_intent in (None, "create_social_post") and any(w in text_lower for w in ["reel", "tiktok", "guion", "script", "video corto"])):
        intent = "create_short_video_script"
    elif body.ui_intent == "ask_advisor" or (body.ui_intent in (None, "create_social_post") and any(w in text_lower for w in ["planear", "plan", "consejo", "ideas", "estrategia", "recomiendame", "¿cómo", "¿a qué", "ayuda", "recomiendas"])):
        intent = "ask_advisor"
    elif body.ui_intent in (None, "create_social_post"):
        intent = "create_social_post"
    else:
        raise ValidationError_("Esta acción todavía no está disponible en el asistente.")
    if intent == "analyze_visual" and len(body.attachment_ids) != 1:
        raise ValidationError_("Selecciona exactamente una imagen para analizar.")
    if intent != "analyze_visual" and body.attachment_ids:
        raise ValidationError_(
            "Los adjuntos sólo están disponibles al analizar una imagen en el asistente."
        )

    record = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint=endpoint,
        key=idempotency_key,
        payload_hash=payload_fingerprint(body.model_dump(mode="json")),
    )
    if record and record.status == "completed" and record.response_json:
        return json.loads(record.response_json)

    try:
        user_msg: Message | None = None
        if idempotency_key and record:
            prior_messages = await get_messages(db, conversation_id)
            for prior_message in reversed(prior_messages):
                if prior_message.role != "user" or not prior_message.metadata_json:
                    continue
                try:
                    metadata = json.loads(prior_message.metadata_json)
                except json.JSONDecodeError:
                    continue
                if metadata.get("idempotency_key") == idempotency_key:
                    user_msg = prior_message
                    break
        if user_msg is None:
            metadata_json: dict[str, object] = {}
            if body.attachment_ids:
                metadata_json["attachment_ids"] = body.attachment_ids
            if idempotency_key:
                metadata_json["idempotency_key"] = idempotency_key
            user_msg = await add_message(
                db,
                conversation_id,
                "user",
                body.text,
                intent=intent,
                metadata_json=metadata_json or None,
            )

        if intent == "analyze_visual":
            # The message that came with the image is the question to answer:
            # an upload is not always a request for the same fixed audit.
            analysis_record, analysis, review_mode = await analyze_authorized_asset(
                db,
                workspace_id=workspace_id,
                asset_id=body.attachment_ids[0],
                question=body.text,
            )
            analysis_data = analysis_to_dict(analysis_record, analysis, review_mode)
            assistant_msg = await add_message(
                db,
                conversation_id,
                "assistant",
                analysis.summary,
                intent="generated_visual_analysis",
                metadata_json={"analysis": analysis_data},
            )
            await db.commit()
            await db.refresh(analysis_record)
            analysis_data["created_at"] = (
                analysis_record.created_at.isoformat() if analysis_record.created_at else None
            )
            return await complete(
                db,
                record,
                {
                    "type": "visual_analysis",
                    "user_message": {"id": user_msg.id, "role": "user", "content": body.text},
                    "assistant_message": {
                        "id": assistant_msg.id,
                        "role": "assistant",
                        "content": analysis.summary,
                    },
                    "analysis": analysis_data,
                },
            )

        if intent == "ask_advisor":
            biz_repo = SqlBusinessContextRepository(db)
            route = await CapabilityRegistry().resolve(Capability.ADVISOR, body.quality_level)
            await ensure_generation_allowed(db, workspace_id=workspace_id)
            provider = get_content_provider(quality_level=route.quality_level)
            service = GenerateAdviceService(biz_repo, provider)
            advice = await service.execute(
                workspace_id=workspace_id,
                business_id=conversation.business_id,
                text=body.text,
                locale=body.locale or "es",
            )
            assistant_msg = await add_message(
                db,
                conversation_id,
                "assistant",
                advice.summary,
                intent="generated_advice",
                metadata_json={"advisor": advice.model_dump()},
            )
            await record_usage(
                db,
                workspace_id=workspace_id,
                user_id=principal.user["id"],
                capability="advisor",
                quality_level=route.quality_level.value,
                provider=provider.provider_name,
                requested_model=provider.model_name,
                metadata=service.usage_metadata,
                outcome="success",
            )
            await db.commit()
            return await complete(
                db,
                record,
                {
                    "type": "advisor",
                    "user_message": {"id": user_msg.id, "role": "user", "content": body.text},
                    "assistant_message": {
                        "id": assistant_msg.id,
                        "role": "assistant",
                        "content": advice.summary,
                    },
                    "advisor": advice.model_dump(),
                },
            )

        biz_repo = SqlBusinessContextRepository(db)
        art_repo = SqlArtifactRepository(db)
        route = await CapabilityRegistry().resolve(Capability.COPYWRITER, body.quality_level)
        await ensure_generation_allowed(db, workspace_id=workspace_id)
        provider = get_content_provider(quality_level=route.quality_level)
        artifact: GeneratedSocialPost | GeneratedShortVideoScript
        assistant_intent: str
        metadata: dict[str, object] | None = None
        provider_called = False
        if intent == "create_short_video_script":
            command = GenerateShortVideoScriptCommand(
                workspace_id=workspace_id,
                business_id=conversation.business_id,
                conversation_id=conversation_id,
                text=body.text,
                platform=body.platform,
                tone=body.tone,
                objective=body.objective,
                locale=body.locale,
            )
            service = GenerateShortVideoScriptService(biz_repo, art_repo, provider)
            provider_called = True
            artifact = await service.execute(command)
            metadata = service.usage_metadata
            assistant_intent = "generated_short_video_script"
        else:
            command = GenerateSocialPostCommand(
                workspace_id=workspace_id,
                business_id=conversation.business_id,
                conversation_id=conversation_id,
                text=body.text,
                platform=body.platform,
                tone=body.tone,
                objective=body.objective,
                locale=body.locale,
            )
            service = GenerateSocialPostService(biz_repo, art_repo, provider)
            provider_called = True
            artifact = await service.execute(command)
            metadata = service.usage_metadata
            assistant_intent = "generated_social_post"
        from sqlalchemy import desc

        art_result = await db.execute(
            select(GeneratedArtifact)
            .where(GeneratedArtifact.conversation_id == conversation_id)
            .order_by(desc(GeneratedArtifact.created_at))
            .limit(1)
        )
        saved_artifact = art_result.scalar_one_or_none()

        await record_usage(
            db,
            workspace_id=workspace_id,
            user_id=principal.user["id"],
            capability="copywriter",
            quality_level=route.quality_level.value,
            provider=provider.provider_name,
            requested_model=provider.model_name,
            metadata=metadata,
            outcome="success",
        )

        assistant_msg = await add_message(
            db,
            conversation_id,
            "assistant",
            artifact.caption,
            intent=assistant_intent,
            metadata_json={
                "artifact_type": artifact.artifact_type,
                "artifact_id": saved_artifact.id if saved_artifact else None,
            },
        )

        response = {
            "type": "artifact",
            "user_message": {
                "id": user_msg.id,
                "role": "user",
                "content": body.text,
            },
            "assistant_message": {
                "id": assistant_msg.id,
                "role": "assistant",
                "content": artifact.caption,
            },
            "artifact": artifact.model_dump(),
            "artifact_id": saved_artifact.id if saved_artifact else None,
        }
        await complete(db, record, response, commit=False)
        await db.commit()
        return response
    except Exception as exc:
        provider = locals().get("provider")
        route = locals().get("route")
        metadata = locals().get("metadata")
        if (
            locals().get("provider_called", False)
            and provider is not None
            and route is not None
        ):
            try:
                await record_usage(
                    db,
                    workspace_id=workspace_id,
                    user_id=principal.user["id"],
                    capability="copywriter",
                    quality_level=route.quality_level.value,
                    provider=provider.provider_name,
                    requested_model=provider.model_name,
                    metadata=metadata,
                    outcome=outcome_for_error(exc),
                )
                await mark_failed(
                    db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key, commit=False
                )
                await db.commit()
            except Exception:
                await recover_failed(
                    db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key
                )
        else:
            await recover_failed(db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key)
        raise


class CreateVariationRequest(BaseModel):
    kind: VariationKind


@router.post("/{conversation_id}/artifacts/{artifact_id}/variations")
async def create_variation_endpoint(
    conversation_id: str,
    artifact_id: str,
    body: CreateVariationRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conv = await get_conversation(db, workspace_id, conversation_id)
    if conv.status != "active":
        raise ValidationError_("Restaura la conversación antes de crear una variación.")

    art_result = await db.execute(
        select(GeneratedArtifact).where(
            GeneratedArtifact.id == artifact_id,
            GeneratedArtifact.conversation_id == conversation_id,
        )
    )
    artifact_record = art_result.scalar_one_or_none()
    if artifact_record is None:
        raise NotFoundError("Artículo")

    endpoint = f"/conversations/{conversation_id}/artifacts/{artifact_id}/variations"
    record = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint=endpoint,
        key=idempotency_key,
        payload_hash=payload_fingerprint({"artifact_id": artifact_id, "kind": body.kind}),
    )
    if record and record.status == "completed" and record.response_json:
        return json.loads(record.response_json)

    version_result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version_number.desc())
        .limit(1)
    )
    current_version = version_result.scalar_one_or_none()
    variation_text_map = {
        "shorter": "Hazlo más corto",
        "more_youthful": "Hazlo más juvenil",
        "more_professional": "Hazlo más profesional",
        "more_friendly": "Hazlo más amigable",
    }
    variation_text = variation_text_map.get(body.kind, "")

    tone_map: dict[VariationKind, str | None] = {
        "shorter": None,
        "more_youthful": "youthful",
        "more_professional": "professional",
        "more_friendly": "friendly",
    }
    variation_tone = tone_map.get(body.kind)

    command = GenerateSocialPostCommand(
        workspace_id=workspace_id,
        business_id=conv.business_id,
        conversation_id=conversation_id,
        text=variation_text,
        tone=variation_tone,
    )

    biz_repo = SqlBusinessContextRepository(db)
    art_repo = SqlArtifactRepository(db)
    await CapabilityRegistry().resolve(Capability.COPYWRITER, QualityLevel.FAST)
    service = GenerateSocialPostService(
        biz_repo,
        art_repo,
        get_content_provider(),
    )
    try:
        artifact = await service.execute_variation(
            command=command,
            artifact_id=artifact_id,
            parent_version_id=current_version.id if current_version else None,
        )
    except Exception:
        await mark_failed(db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key)
        raise
    await db.commit()

    return await complete(
        db,
        record,
        {
            "type": "artifact",
            "artifact": artifact.model_dump(),
            "artifact_id": artifact_id,
            "version_number": (current_version.version_number + 1) if current_version else 1,
        },
    )
