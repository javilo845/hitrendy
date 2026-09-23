from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="HiTrendy Demo API", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class BusinessProfile(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=80)
    city: str = Field(min_length=1, max_length=100)
    primary_product: str = Field(min_length=1, max_length=240)
    target_audience: str = Field(min_length=1, max_length=500)
    platform: Literal["instagram", "facebook", "tiktok", "whatsapp"] = "instagram"
    objective: Literal["reach", "engagement", "sales", "store_visits"] = "store_visits"
    tone: Literal["friendly", "professional", "youthful", "elegant", "fun", "direct"] = "youthful"


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    business: BusinessProfile


class SocialPost(BaseModel):
    artifact_type: Literal["social_post"] = "social_post"
    platform: str
    hook: str
    caption: str
    call_to_action: str
    hashtags: list[str]
    visual_direction: str
    format_recommendation: str
    assumptions: list[str]


def create_demo_post(request: ChatRequest) -> SocialPost:
    business = request.business
    product = business.primary_product.strip()
    name = business.name.strip()
    city = business.city.strip()
    audience = business.target_audience.strip()

    objective_line = {
        "reach": "Compártelo con alguien que siempre busca probar algo nuevo.",
        "engagement": "Cuéntanos en los comentarios cómo lo disfrutarías.",
        "sales": "Escríbenos para conocer la disponibilidad.",
        "store_visits": "Visítanos esta semana y pruébalo en el local.",
    }[business.objective]

    tone_hook = {
        "friendly": f"Tenemos algo nuevo para compartir contigo: {product}",
        "professional": f"Presentamos nuestra nueva propuesta: {product}",
        "youthful": f"Tu próximo antojo ya tiene nombre: {product} ✨",
        "elegant": f"Descubre una nueva forma de disfrutar {product}",
        "fun": f"Alerta de antojo: llegó {product} 😋",
        "direct": f"Ya puedes probar {product}",
    }[business.tone]

    platform_format = {
        "instagram": "reel",
        "facebook": "static_post",
        "tiktok": "short_video",
        "whatsapp": "static_post",
    }[business.platform]

    caption = (
        f"En {name} preparamos {product} pensando en {audience.lower()}. "
        f"Una idea para salir de la rutina y disfrutar en {city}. {objective_line}"
    )

    safe_tag_name = "".join(ch for ch in name.title().replace(" ", "") if ch.isalnum()) or "HiTrendy"
    safe_tag_city = "".join(ch for ch in city.title().replace(" ", "") if ch.isalnum()) or "Local"

    return SocialPost(
        platform=business.platform,
        hook=tone_hook,
        caption=caption,
        call_to_action=objective_line,
        hashtags=[f"#{safe_tag_name}", f"#{safe_tag_city}", "#HechoParaTi"],
        visual_direction=(
            f"Muestra el producto en primer plano, una toma breve de la preparación y una escena final "
            f"con el ambiente de {name}. Mantén texto corto y alto contraste."
        ),
        format_recommendation=platform_format,
        assumptions=[
            "La demo no inventó precios, descuentos ni horarios.",
            f"Se utilizó el tono {business.tone} y el objetivo {business.objective} del perfil.",
        ],
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": "demo"}


@app.post("/api/demo/generate", response_model=SocialPost)
def generate(request: ChatRequest) -> SocialPost:
    if "garantiza" in request.text.lower() and "ventas" in request.text.lower():
        raise HTTPException(
            status_code=422,
            detail="HiTrendy puede crear un borrador, pero no garantizar resultados comerciales.",
        )
    return create_demo_post(request)
