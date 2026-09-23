from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.repository import (
    brand_profile_to_dict,
    business_to_dict,
    create_business,
    get_brand_profile,
    get_business,
    update_business,
    upsert_brand_profile,
)
from app.conversations.idempotency import (
    complete,
    mark_failed,
    payload_fingerprint,
    recover_failed,
    reserve,
)
from app.conversations.repository import SqlBusinessContextRepository
from app.core.capabilities import Capability, CapabilityRegistry, QualityLevel
from app.dependencies import CurrentPrincipal, get_current_principal, get_db, require_workspace
from app.domain.models import Category, Objective, Platform, Tone
from app.providers.factory import get_content_provider
from app.services.ai_usage import outcome_for_error, record_usage
from app.services.generate_advice import GenerateAdviceService
from app.services.usage_policy import ensure_generation_allowed

router = APIRouter(prefix="/businesses", tags=["business"])


class CreateBusinessRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: Category
    country: str = Field(min_length=2, max_length=80)
    city: str = Field(min_length=1, max_length=100)
    description: str | None = Field(None, max_length=1000)
    primary_product: str = Field(min_length=1, max_length=240)
    target_audience: str = Field(min_length=1, max_length=500)
    preferred_platforms: list[Platform] = Field(min_length=1)
    primary_objective: Objective


class UpdateBusinessRequest(BaseModel):
    name: str | None = Field(None, max_length=120)
    category: Category | None = None
    country: str | None = Field(None, max_length=80)
    city: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=1000)
    primary_product: str | None = Field(None, max_length=240)
    target_audience: str | None = Field(None, max_length=500)
    preferred_platforms: list[Platform] | None = None
    primary_objective: Objective | None = None
    content_locale: str | None = Field(None, pattern=r"^(es|en|pt)$")


class UpsertBrandProfileRequest(BaseModel):
    voice_tones: list[Tone] = Field(min_length=1, max_length=3)
    value_proposition: str = Field(min_length=1, max_length=500)
    preferred_words: list[str] = Field(default_factory=list, max_length=30)
    forbidden_words: list[str] = Field(default_factory=list, max_length=30)
    primary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def normalize_words(self) -> UpsertBrandProfileRequest:
        def cleaned(words: list[str]) -> list[str]:
            output: list[str] = []
            for word in words:
                value = word.strip()
                if not value or len(value) > 80:
                    raise ValueError("Las palabras de marca deben tener entre 1 y 80 caracteres.")
                if value.casefold() not in {item.casefold() for item in output}:
                    output.append(value)
            return output
        self.preferred_words = cleaned(self.preferred_words)
        self.forbidden_words = cleaned(self.forbidden_words)
        if {word.casefold() for word in self.preferred_words} & {word.casefold() for word in self.forbidden_words}:
            raise ValueError("Una palabra no puede ser preferida y prohibida a la vez.")
        return self


class AdvisorRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    quality_level: QualityLevel = QualityLevel.FAST
    locale: str = Field(default="es", pattern=r"^(es|en|pt)$")


@router.get("")
async def list_businesses_endpoint(
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    from sqlalchemy import select

    from app.business.models import Business

    result = await db.execute(select(Business).where(Business.workspace_id == workspace_id))
    return [business_to_dict(b) for b in result.scalars().all()]


@router.post("", status_code=201)
async def create_business_endpoint(
    body: CreateBusinessRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    business = await create_business(db, workspace_id, body.model_dump())
    await db.commit()
    return business_to_dict(business)


@router.get("/{business_id}")
async def get_business_endpoint(
    business_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    business = await get_business(db, workspace_id, business_id)
    return business_to_dict(business)


@router.patch("/{business_id}")
async def update_business_endpoint(
    business_id: str,
    body: UpdateBusinessRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    clean = {k: v for k, v in body.model_dump(exclude_none=True).items() if v is not None}
    business = await update_business(db, workspace_id, business_id, clean)
    await db.commit()
    return business_to_dict(business)


@router.put("/{business_id}/brand-profile")
async def upsert_brand_profile_endpoint(
    business_id: str,
    body: UpsertBrandProfileRequest,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = await upsert_brand_profile(db, workspace_id, business_id, body.model_dump())
    await db.commit()
    return brand_profile_to_dict(profile)


@router.get("/{business_id}/brand-profile")
async def get_brand_profile_endpoint(
    business_id: str,
    workspace_id: str = Depends(require_workspace),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = await get_brand_profile(db, workspace_id, business_id)
    return brand_profile_to_dict(profile)


@router.post("/{business_id}/advisor")
async def generate_advisor_endpoint(
    business_id: str,
    body: AdvisorRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key", max_length=160),
    workspace_id: str = Depends(require_workspace),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    endpoint = f"/businesses/{business_id}/advisor"
    record = await reserve(
        db,
        workspace_id=workspace_id,
        endpoint=endpoint,
        key=idempotency_key,
        payload_hash=payload_fingerprint(body.model_dump(mode="json")),
    )
    if record and record.status == "completed" and record.response_json:
        return json.loads(record.response_json)
    route = None
    provider = None
    service = None
    provider_called = False
    try:
        await get_business(db, workspace_id, business_id)
        route = await CapabilityRegistry().resolve(Capability.ADVISOR, body.quality_level)
        await ensure_generation_allowed(db, workspace_id=workspace_id)
        provider = get_content_provider(quality_level=route.quality_level)
        service = GenerateAdviceService(SqlBusinessContextRepository(db), provider)
        provider_called = True
        result = await service.execute(
            workspace_id=workspace_id, business_id=business_id, text=body.text, locale=body.locale
        )
    except Exception as exc:
        if provider_called and provider is not None and route is not None and service is not None:
            try:
                await record_usage(
                    db, workspace_id=workspace_id, user_id=principal.user["id"], capability="advisor",
                    quality_level=route.quality_level.value, provider=provider.provider_name,
                    requested_model=provider.model_name, metadata=service.usage_metadata,
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
    try:
        await record_usage(
            db, workspace_id=workspace_id, user_id=principal.user["id"], capability="advisor",
            quality_level=route.quality_level.value, provider=provider.provider_name,
            requested_model=provider.model_name, metadata=service.usage_metadata, outcome="success",
        )
        response = {"advisor": result.model_dump()}
        await complete(db, record, response, commit=False)
        await db.commit()
    except Exception:
        await recover_failed(db, workspace_id=workspace_id, endpoint=endpoint, key=idempotency_key)
        raise
    return response
