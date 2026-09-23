from __future__ import annotations

import json
from datetime import UTC, datetime
from difflib import SequenceMatcher
from typing import Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.models import Business
from app.conversations.idempotency import complete, payload_fingerprint, recover_failed, reserve
from app.conversations.models import ArtifactEvent, ArtifactVersion, Conversation, GeneratedArtifact
from app.conversations.repository import SqlArtifactRepository
from app.core.errors import AppError, ConflictError, NotFoundError, ValidationError_
from app.dependencies import get_db, require_workspace
from app.domain.models import GeneratedShortVideoScript, GeneratedSocialPost, VideoScene
from app.projects.models import CreationFlowEvent, Project
from app.templates.canva_catalog import get_canva_template
from app.templates.repository import get_template

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    artifact_id: str | None = Field(None, min_length=1)
    template_id: str | None = Field(None, min_length=1)
    name: str | None = Field(None, max_length=240)
    business_id: str | None = Field(None, min_length=1)


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(None, max_length=240)
    status: Literal["active", "archived"] | None = None


class StartCreationFlowRequest(BaseModel):
    business_id: str = Field(min_length=1)


class CompleteCreationFlowRequest(BaseModel):
    status: Literal["generation_completed", "completed", "failed"]


def project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "workspace_id": p.workspace_id,
        "business_id": p.business_id,
        "name": p.name,
        "artifact_id": p.artifact_id,
        "source_template_id": p.source_template_id,
        "platform": p.platform,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _load_artifact_content_json(snapshot: str | None) -> dict | None:
    if snapshot is None:
        return None
    try:
        return json.loads(snapshot)
    except (json.JSONDecodeError, TypeError):
        return None


def _edit_magnitude_percent(previous_content: str | None, updated_content: str) -> int:
    if not previous_content:
        return 100
    return round((1 - SequenceMatcher(None, previous_content, updated_content).ratio()) * 100)


@router.post("", status_code=201)
async def create_project_endpoint(
    body: CreateProjectRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    endpoint = "/projects"
    request_payload = body.model_dump(mode="json")
    request_hash = payload_fingerprint(request_payload)
    record = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint=endpoint,
        key=idempotency_key,
        payload_hash=request_hash,
        commit=False,
    )
    if record and record.status == "completed" and record.response_json:
        return json.loads(record.response_json)

    content: dict | GeneratedSocialPost | None = None
    artifact_id: str | None = None
    platform: str = "instagram"
    business_id: str | None = body.business_id

    try:
        template_data: dict | None = None
        if body.template_id:
            # The Canva catalogue is browse-only: its entries list and resolve
            # like any other template but carry no editable slots, so a project
            # started from one would open an empty composer. Saying that is the
            # point -- letting get_template raise would answer "no existe" about
            # an id the catalogue endpoint just handed out.
            if get_canva_template(body.template_id) is not None:
                raise ValidationError_(
                    "Esa plantilla de Canva se edita en Canva. "
                    "Elige una plantilla de HiTrendy para crear un proyecto."
                )
            template_data = await get_template(db, body.template_id)

        if body.template_id and not body.artifact_id:
            if business_id is None:
                raise ValidationError_("Selecciona el negocio para el proyecto.")
            business_result = await db.execute(
                select(Business.id).where(
                    Business.id == business_id, Business.workspace_id == workspace_id
                )
            )
            if business_result.scalar_one_or_none() is None:
                raise NotFoundError("Negocio")
            assert template_data is not None
            platform = template_data["platforms"][0] if template_data["platforms"] else "instagram"
            title = body.name or template_data["title"]
            content = GeneratedSocialPost(
                platform=platform,
                hook=title,
                caption="Escribe aquí el texto principal de tu publicación.",
                call_to_action="",
                hashtags=[],
                visual_direction="Añade una indicación visual para esta plantilla.",
                format_recommendation=template_data["formats"][0] if template_data["formats"] else "static_post",
                assumptions=[f"Proyecto iniciado desde la plantilla {template_data['title']}."],
            )
            template_artifact = GeneratedArtifact(artifact_type=content.artifact_type, platform=platform, objective=template_data["objective"], model_provider="template", model_name="template-v1", prompt_version=None, business_profile_version=1)
            db.add(template_artifact)
            await db.flush()
            version = ArtifactVersion(artifact_id=template_artifact.id, version_number=1, content_json=content.model_dump_json(), user_edited=False)
            db.add(version)
            await db.flush()
            template_artifact.active_version_id = version.id
            artifact_id = template_artifact.id
        elif body.artifact_id:
            artifact_result = await db.execute(select(GeneratedArtifact, Conversation).join(Conversation, Conversation.id == GeneratedArtifact.conversation_id).where(GeneratedArtifact.id == body.artifact_id, Conversation.workspace_id == workspace_id))
            row = artifact_result.one_or_none()
            if row is None:
                raise NotFoundError("Artículo")
            artifact, conv = row
            if artifact.project_id:
                raise ConflictError("El artículo ya está asociado a otro proyecto.")
            business_id, platform, artifact_id = conv.business_id, artifact.platform, artifact.id
            version = await db.scalar(select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id).order_by(ArtifactVersion.version_number.desc()).limit(1))
            content = json.loads(version.content_json) if version else None
            title = body.name or (content.get("hook", "")[:100] if isinstance(content, dict) else "")
            if template_data:
                if template_data["platforms"] != ["instagram"] or template_data["aspect_ratio"] != "4:5":
                    raise ValidationError_("La plantilla no es compatible con el post de Instagram 4:5.")
                platform = "instagram"
        else:
            raise NotFoundError("Artículo o plantilla")

        if not title:
            title = "Proyecto sin título"
        project = Project(workspace_id=workspace_id, business_id=business_id, name=title, artifact_id=artifact_id, source_template_id=body.template_id, platform=platform)
        db.add(project)
        await db.flush()
        if artifact_id:
            art = await db.scalar(select(GeneratedArtifact).where(GeneratedArtifact.id == artifact_id))
            if art is not None:
                art.project_id = project.id
        await db.refresh(project)
        response = project_to_dict(project)
        response["artifact_snapshot"] = content.model_dump() if isinstance(content, GeneratedSocialPost) else content
        await complete(db, record, response, commit=False)
        await db.commit()
        return response
    except Exception:
        await recover_failed(db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key, payload_hash=request_hash)
        raise


@router.post("/flow-events", status_code=201)
async def start_creation_flow_endpoint(
    body: StartCreationFlowRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    exists = await db.scalar(
        select(Business.id).where(Business.id == body.business_id, Business.workspace_id == workspace_id)
    )
    if exists is None:
        raise NotFoundError("Negocio")
    event = await db.scalar(
        select(CreationFlowEvent)
        .where(
            CreationFlowEvent.workspace_id == workspace_id,
            CreationFlowEvent.business_id == body.business_id,
            CreationFlowEvent.flow_key == idempotency_key,
        )
        .limit(1)
    ) if idempotency_key else None
    if event is None:
        event = await db.scalar(
        select(CreationFlowEvent)
        .where(
            CreationFlowEvent.workspace_id == workspace_id,
            CreationFlowEvent.business_id == body.business_id,
            CreationFlowEvent.completion_status.in_(["started", "generation_completed"]),
        )
        .order_by(CreationFlowEvent.flow_started_at.desc())
        .limit(1)
        )
    if event is not None:
        return {"id": event.id, "flow_started_at": event.flow_started_at.isoformat()}
    event = CreationFlowEvent(
        workspace_id=workspace_id, business_id=body.business_id, flow_key=idempotency_key
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return {"id": event.id, "flow_started_at": event.flow_started_at.isoformat()}


@router.patch("/flow-events/{event_id}")
async def complete_creation_flow_endpoint(
    event_id: str,
    body: CompleteCreationFlowRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    event = await db.scalar(
        select(CreationFlowEvent).where(
            CreationFlowEvent.id == event_id, CreationFlowEvent.workspace_id == workspace_id
        )
    )
    if event is None:
        raise NotFoundError("Flujo de creación")
    if event.completion_status not in {"completed", "failed"}:
        now = datetime.now(UTC)
        if body.status == "generation_completed":
            if event.first_generation_completed_at is None:
                event.first_generation_completed_at = now
            event.completion_status = "generation_completed"
        elif body.status in {"completed", "failed"}:
            if body.status == "completed" and event.first_generation_completed_at is None:
                event.first_generation_completed_at = now
            event.completion_status = body.status
            if event.elapsed_seconds is None:
                event.elapsed_seconds = max(0, int((now - event.flow_started_at).total_seconds()))
        await db.commit()
    return {
        "id": event.id,
        "flow_started_at": event.flow_started_at.isoformat(),
        "first_generation_completed_at": event.first_generation_completed_at.isoformat()
        if event.first_generation_completed_at
        else None,
        "elapsed_seconds": event.elapsed_seconds,
        "completion_status": event.completion_status,
    }


@router.get("")
async def list_projects_endpoint(
    status: str | None = None,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    query = select(Project).where(Project.workspace_id == workspace_id)
    if status:
        query = query.where(Project.status == status)
    query = query.order_by(Project.updated_at.desc()).limit(20)
    result = await db.execute(query)
    projects = result.scalars().all()

    output = []
    for p in projects:
        data = project_to_dict(p)
        if p.artifact_id:
            version_result = await db.execute(
                select(ArtifactVersion)
                .where(ArtifactVersion.artifact_id == p.artifact_id)
                .order_by(ArtifactVersion.version_number.desc())
                .limit(1)
            )
            version = version_result.scalar_one_or_none()
            content: dict | None = json.loads(version.content_json) if version else None
            data["artifact_snapshot"] = content
        output.append(data)
    return output


@router.get("/{project_id}")
async def get_project_endpoint(
    project_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Proyecto")

    data = project_to_dict(project)

    if project.artifact_id:
        version_result = await db.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == project.artifact_id)
            .order_by(ArtifactVersion.version_number.desc())
            .limit(1)
        )
        version = version_result.scalar_one_or_none()
        content: dict | None = json.loads(version.content_json) if version else None
        data["artifact_snapshot"] = content

    return data


@router.patch("/{project_id}")
async def update_project_endpoint(
    project_id: str,
    body: UpdateProjectRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Proyecto")

    if body.name is not None:
        project.name = body.name
    if body.status is not None:
        project.status = body.status

    await db.commit()
    await db.refresh(project)
    return project_to_dict(project)


@router.post("/{project_id}/duplicate", status_code=201)
async def duplicate_project_endpoint(
    project_id: str,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    endpoint = f"/projects/{project_id}/duplicate"
    request_hash = payload_fingerprint({"project_id": project_id})
    record = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint=endpoint,
        key=idempotency_key,
        payload_hash=request_hash,
        commit=False,
    )
    if record and record.status == "completed" and record.response_json:
        return json.loads(record.response_json)
    try:
        result = await db.execute(
            select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
        )
        project = result.scalar_one_or_none()
        if project is None:
            raise NotFoundError("Proyecto")

        duplicated_artifact_id: str | None = None
        duplicated_artifact: GeneratedArtifact | None = None
        if project.artifact_id:
            source_artifact = (
            await db.execute(
                select(GeneratedArtifact).where(GeneratedArtifact.id == project.artifact_id)
            )
            ).scalar_one_or_none()
            if source_artifact is None:
                raise NotFoundError("Artículo")
            source_version = (
            await db.execute(
                select(ArtifactVersion)
                .where(ArtifactVersion.artifact_id == source_artifact.id)
                .order_by(ArtifactVersion.version_number.desc())
                .limit(1)
            )
            ).scalar_one_or_none()
            if source_version is None:
                raise NotFoundError("Versión")
            duplicated_artifact = GeneratedArtifact(
            conversation_id=source_artifact.conversation_id,
            artifact_type=source_artifact.artifact_type,
            platform=source_artifact.platform,
            objective=source_artifact.objective,
            model_provider=source_artifact.model_provider,
            model_name=source_artifact.model_name,
            prompt_version=source_artifact.prompt_version,
            business_profile_version=source_artifact.business_profile_version,
            )
            db.add(duplicated_artifact)
            await db.flush()
            duplicated_version = ArtifactVersion(
            artifact_id=duplicated_artifact.id,
            version_number=1,
            content_json=source_version.content_json,
            user_edited=source_version.user_edited,
            parent_version_id=source_version.id,
            )
            db.add(duplicated_version)
            await db.flush()
            duplicated_artifact.active_version_id = duplicated_version.id
            duplicated_artifact_id = duplicated_artifact.id

        duplicate = Project(
        workspace_id=workspace_id,
        business_id=project.business_id,
        name=f"{project.name} (copia)",
        artifact_id=duplicated_artifact_id,
        source_template_id=project.source_template_id,
        platform=project.platform,
        status="active",
        )
        db.add(duplicate)
        await db.flush()
        if duplicated_artifact:
            duplicated_artifact.project_id = duplicate.id
        await db.refresh(duplicate)
        response = project_to_dict(duplicate)
        await complete(db, record, response, commit=False)
        await db.commit()
        return response
    except Exception:
        await recover_failed(db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key, payload_hash=request_hash)
        raise


@router.get("/{project_id}/export")
async def export_project_endpoint(
    project_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Proyecto")
    exported = project_to_dict(project)
    if project.artifact_id:
        version_result = await db.execute(
            select(ArtifactVersion)
            .where(ArtifactVersion.artifact_id == project.artifact_id)
            .order_by(ArtifactVersion.version_number.desc())
            .limit(1)
        )
        version = version_result.scalar_one_or_none()
        exported["content"] = _load_artifact_content_json(version.content_json if version else None)
        exported["version_number"] = version.version_number if version else None
    return {"format": "hitrendy-project/v1", "project": exported}


class UpdateSocialPostVersionRequest(BaseModel):
    artifact_type: Literal["social_post"] = "social_post"
    hook: str = Field(min_length=1, max_length=180)
    caption: str = Field(min_length=1, max_length=2200)
    call_to_action: str = Field(max_length=240)
    hashtags: list[str] = Field(max_length=5)
    visual_direction: str = Field(min_length=1, max_length=700)
    format_recommendation: str


class UpdateShortVideoScriptVersionRequest(BaseModel):
    artifact_type: Literal["short_video_script"] = "short_video_script"
    hook: str = Field(min_length=1, max_length=180)
    duration_seconds: int = Field(ge=5, le=90)
    scenes: list[VideoScene] = Field(min_length=2, max_length=8)
    call_to_action: str = Field(min_length=1, max_length=240)
    caption: str = Field(min_length=1, max_length=2200)
    assumptions: list[str] = Field(default_factory=list, max_length=10)


@router.put("/{project_id}/artifact-version")
async def update_artifact_version_endpoint(
    project_id: str,
    body: UpdateSocialPostVersionRequest | UpdateShortVideoScriptVersionRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Proyecto")
    if not project.artifact_id:
        raise NotFoundError("Artículo")

    artifact_record = (
        await db.execute(
            select(GeneratedArtifact).where(GeneratedArtifact.id == project.artifact_id)
        )
    ).scalar_one_or_none()
    if artifact_record is None:
        raise NotFoundError("Artículo")
    if artifact_record.artifact_type != body.artifact_type:
        raise ValidationError_("El contenido no corresponde al tipo de este proyecto.")

    version_result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == project.artifact_id)
        .order_by(ArtifactVersion.version_number.desc())
        .limit(1)
    )
    current_version = version_result.scalar_one_or_none()

    if isinstance(body, UpdateSocialPostVersionRequest):
        content = GeneratedSocialPost(
            platform=artifact_record.platform,
            hook=body.hook,
            caption=body.caption,
            call_to_action=body.call_to_action,
            hashtags=body.hashtags,
            visual_direction=body.visual_direction,
            format_recommendation=body.format_recommendation,
        )
    else:
        content = GeneratedShortVideoScript(
            platform=artifact_record.platform,
            hook=body.hook,
            duration_seconds=body.duration_seconds,
            scenes=body.scenes,
            call_to_action=body.call_to_action,
            caption=body.caption,
            assumptions=body.assumptions,
        )

    repo = SqlArtifactRepository(db)
    serialized_content = content.model_dump_json()
    edit_magnitude_percent = _edit_magnitude_percent(
        current_version.content_json if current_version else None, serialized_content
    )
    await repo.add_artifact_version(
        artifact_id=project.artifact_id,
        content=content,
        user_edited=True,
        parent_version_id=current_version.id if current_version else None,
    )
    db.add(
        ArtifactEvent(
            artifact_id=project.artifact_id,
            event_type="edited",
            magnitude_percent=edit_magnitude_percent,
        )
    )
    await db.commit()

    return {
        "version": content.model_dump(),
        "version_number": (current_version.version_number + 1) if current_version else 1,
        "edit_magnitude_percent": edit_magnitude_percent,
    }


@router.get("/{project_id}/versions")
async def list_project_versions_endpoint(
    project_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Proyecto")
    if not project.artifact_id:
        return []
    result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == project.artifact_id)
        .order_by(ArtifactVersion.version_number.desc())
    )
    return [
        {
            "id": version.id,
            "version_number": version.version_number,
            "user_edited": version.user_edited,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }
        for version in result.scalars().all()
    ]


@router.post("/{project_id}/versions/{version_id}/restore")
async def restore_project_version_endpoint(
    project_id: str,
    version_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Proyecto")
    if not project.artifact_id:
        raise NotFoundError("Artículo")

    artifact_record = (
        await db.execute(
            select(GeneratedArtifact).where(GeneratedArtifact.id == project.artifact_id)
        )
    ).scalar_one_or_none()
    if artifact_record is None:
        raise NotFoundError("Artículo")

    target_result = await db.execute(
        select(ArtifactVersion).where(
            ArtifactVersion.id == version_id,
            ArtifactVersion.artifact_id == project.artifact_id,
        )
    )
    target_version = target_result.scalar_one_or_none()
    if target_version is None:
        raise NotFoundError("Versión")

    latest_result = await db.execute(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == project.artifact_id)
        .order_by(ArtifactVersion.version_number.desc())
        .limit(1)
    )
    latest_version = latest_result.scalar_one_or_none()
    if latest_version and latest_version.id == target_version.id:
        raise ValidationError_("Esta versión ya es la versión actual.")
    try:
        if artifact_record.artifact_type == "social_post":
            restored_content = GeneratedSocialPost.model_validate_json(target_version.content_json)
        elif artifact_record.artifact_type == "short_video_script":
            restored_content = GeneratedShortVideoScript.model_validate_json(
                target_version.content_json
            )
        else:
            raise AppError(
                "VERSION_UNAVAILABLE",
                "Este tipo de contenido todavía no se puede restaurar.",
                status_code=409,
                retryable=False,
            )
    except PydanticValidationError as exc:
        raise AppError(
            "VERSION_UNAVAILABLE",
            "No pudimos recuperar esta versión del proyecto.",
            status_code=409,
            retryable=False,
        ) from exc

    repo = SqlArtifactRepository(db)
    await repo.add_artifact_version(
        artifact_id=project.artifact_id,
        content=restored_content,
        user_edited=True,
        parent_version_id=latest_version.id if latest_version else None,
    )
    await db.commit()

    return {
        "version": restored_content.model_dump(),
        "version_number": (latest_version.version_number + 1) if latest_version else 1,
        "restored_from_version": target_version.version_number,
    }
