from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx

from app.core.errors import AppError
from app.domain.models import AdvisorResponse, GeneratedSocialPost
from app.generation.contracts import (
    AdvisorModelRequest,
    ShortVideoScriptModelRequest,
    SocialPostModelRequest,
)
from app.generation.prompt_registry import get_short_video_script_prompt, get_social_copy_prompt

# Families that expose no sampling controls. Matched by prefix so future point
# releases (gpt-5.1-mini, o3-pro) are covered without another edit here.
_FIXED_TEMPERATURE_MODEL_PREFIXES = ("gpt-5", "o1", "o3", "o4")


def _rejects_temperature(model_name: str) -> bool:
    """Whether the model refuses an explicit ``temperature``.

    OpenRouter-style identifiers carry a vendor prefix (``openai/gpt-5-mini``),
    so the comparison runs on the segment after the last slash.
    """

    return model_name.rsplit("/", 1)[-1].strip().lower().startswith(
        _FIXED_TEMPERATURE_MODEL_PREFIXES
    )


def _to_strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Rewrite a Pydantic JSON schema into the subset ``strict`` mode accepts.

    Pydantic leaves a field out of ``required`` when it has a default, and emits
    the default alongside it. Strict structured output rejects both: every key in
    ``properties`` must be listed in ``required``, and ``default`` is not part of
    the supported keyword set. Sending the schema unchanged fails the request with
    an HTTP 400, so the whole generation dies instead of merely being unvalidated.

    Widening ``required`` costs nothing here because the fields carrying defaults
    (``artifact_type``, ``assumptions``) are ones the model should always emit
    anyway; the Pydantic default stays as the fallback when the provider is not
    running in structured mode. Returns a copy — the caller's schema is untouched.
    """

    strict: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "default":
            continue
        if isinstance(value, dict):
            strict[key] = _to_strict_schema(value)
        elif isinstance(value, list):
            strict[key] = [
                _to_strict_schema(item) if isinstance(item, dict) else item for item in value
            ]
        else:
            strict[key] = value

    if strict.get("type") == "object" and isinstance(strict.get("properties"), dict):
        strict["required"] = list(strict["properties"])
        strict["additionalProperties"] = False
    return strict


def _normalize_social_post_payload(raw: Any, request: SocialPostModelRequest) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    inner = raw.get("content") or raw.get("data") or raw.get("post") or {}
    if isinstance(inner, dict):
        merged = {**raw, **inner}
    else:
        merged = dict(raw)

    caption = merged.get("caption") or ""
    if isinstance(caption, dict):
        caption = " ".join(str(v) for v in caption.values())
    caption_str = str(caption).strip() or f"En {request.business.name} te esperamos con la mejor atención."

    hook = merged.get("hook") or ""
    if not hook or not str(hook).strip():
        first_line = caption_str.split("\n")[0]
        hook = first_line[:120] if first_line else f"¡Descubre lo nuevo de {request.business.name}! ✨"
    hook_str = str(hook).strip()

    cta = merged.get("call_to_action") or ""
    if not cta or not str(cta).strip():
        cta = "¡Visítanos hoy o escríbenos para más información!"
    cta_str = str(cta).strip()

    raw_tags = merged.get("hashtags")
    tags = []
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            tag_str = str(tag).strip()
            if not tag_str:
                continue
            if not tag_str.startswith("#"):
                tag_str = f"#{tag_str}"
            clean_tag = "".join(tag_str.split())
            if len(clean_tag) > 1:
                tags.append(clean_tag[:100])
    elif isinstance(raw_tags, str):
        for word in raw_tags.split():
            if word.startswith("#") and len(word) > 1:
                tags.append(word[:100])
    if not tags:
        clean_biz = "".join(c for c in request.business.name if c.isalnum())
        tags = [f"#{clean_biz}" if clean_biz else "#HiTrendy", "#NegocioLocal", "#Calidad"]

    vis = merged.get("visual_direction")
    if isinstance(vis, dict):
        vis_str = " ".join(f"{k}: {v}" for k, v in vis.items())
    elif isinstance(vis, str) and vis.strip():
        vis_str = vis.strip()
    else:
        vis_str = f"Brief visual 4:5 para Canva: {request.business.primary_product} en plano principal, estética limpia y texto sugerido '{request.business.name}'."

    assumptions = merged.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions:
        assumptions = [f"Se utilizó el tono {request.tone} y el objetivo {request.objective} del perfil."]
    else:
        assumptions = [str(a)[:300] for a in assumptions if str(a).strip()]

    result = {
        "artifact_type": "social_post",
        "platform": merged.get("platform") if merged.get("platform") in ("instagram", "facebook", "tiktok", "linkedin", "twitter", "pinterest") else request.platform,
        "hook": hook_str[:140],
        "caption": caption_str[:2200],
        "call_to_action": cta_str[:240],
        "hashtags": tags[:5],
        "visual_direction": vis_str[:700],
        "format_recommendation": (
            merged.get("format_recommendation")
            if merged.get("format_recommendation") in ("static_post", "carousel", "story", "reel", "short_video", "text_post")
            else "static_post"
        ),
        "assumptions": assumptions[:10],
    }
    if "__provider_metadata" in raw:
        result["__provider_metadata"] = raw["__provider_metadata"]
    return result


def _normalize_video_script_payload(raw: Any, request: ShortVideoScriptModelRequest) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    inner = raw.get("content") or raw.get("data") or raw.get("script") or {}
    if isinstance(inner, dict):
        merged = {**raw, **inner}
    else:
        merged = dict(raw)

    raw_scenes = merged.get("scenes")
    scenes = []
    if isinstance(raw_scenes, list) and raw_scenes:
        for idx, scene in enumerate(raw_scenes, start=1):
            if isinstance(scene, dict):
                scenes.append({
                    "scene_number": int(scene.get("scene_number") or idx),
                    "duration_seconds": int(scene.get("duration_seconds") or 5),
                    "visual_description": str(scene.get("visual_description") or f"Toma atractiva de {request.business.primary_product}.").strip()[:300],
                    "spoken_text": str(scene.get("spoken_text") or "Descubre nuestra calidad única.").strip()[:300],
                    "on_screen_text": str(scene.get("on_screen_text") or request.business.name).strip()[:100],
                })
    if not scenes:
        scenes = [
            {"scene_number": 1, "duration_seconds": 5, "visual_description": f"Hook visual llamativo mostrando {request.business.primary_product}.", "spoken_text": "¿Conocías esto?", "on_screen_text": "¡NUEVO!"},
            {"scene_number": 2, "duration_seconds": 10, "visual_description": "Detalle del proceso o producto terminado.", "spoken_text": "Hecho con la mejor dedicación para ti.", "on_screen_text": request.business.name},
            {"scene_number": 3, "duration_seconds": 5, "visual_description": "Llamado a la acción en pantalla con datos de contacto.", "spoken_text": "¡Escríbenos hoy!", "on_screen_text": "Pide aquí ↗"},
        ]

    raw_tags = merged.get("hashtags")
    tags = []
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            tag_str = str(tag).strip()
            if not tag_str:
                continue
            if not tag_str.startswith("#"):
                tag_str = f"#{tag_str}"
            clean_tag = "".join(tag_str.split())
            if len(clean_tag) > 1:
                tags.append(clean_tag[:100])
    if not tags:
        tags = ["#ReelsViral", "#Negocio", "#Tendencia"]

    assumptions = merged.get("assumptions")
    if not isinstance(assumptions, list) or not assumptions:
        assumptions = [f"Se utilizó el tono {request.tone} y el objetivo {request.objective} del perfil."]
    else:
        assumptions = [str(a)[:300] for a in assumptions if str(a).strip()]

    result = {
        "artifact_type": "short_video_script",
        "platform": merged.get("platform") if merged.get("platform") in ("instagram", "facebook", "tiktok", "linkedin", "twitter", "pinterest") else request.platform,
        "hook": str(merged.get("hook") or f"¿Buscando lo mejor en {request.business.name}? Mira esto 👀").strip()[:140],
        "duration_seconds": int(merged.get("duration_seconds") or sum(s["duration_seconds"] for s in scenes)),
        "scenes": scenes,
        "audio_direction": str(merged.get("audio_direction") or "Música en tendencia de ritmo alegre con locución clara y dinámica.").strip()[:300],
        "caption": str(merged.get("caption") or f"Lo que estabas esperando en {request.business.name}. ¡Comenta para más info!").strip()[:2200],
        "call_to_action": str(merged.get("call_to_action") or "¡Síguenos y comenta 'INFO' para enviarte los detalles!").strip()[:240],
        "hashtags": tags[:5],
        "assumptions": assumptions[:10],
    }
    if "__provider_metadata" in raw:
        result["__provider_metadata"] = raw["__provider_metadata"]
    return result


def _normalize_advice_payload(raw: Any, request: AdvisorModelRequest) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    inner = raw.get("content") or raw.get("data") or raw.get("advice") or {}
    if isinstance(inner, dict):
        merged = {**raw, **inner}
    else:
        merged = dict(raw)

    raw_recs = merged.get("recommendations")
    recs = []
    if isinstance(raw_recs, list) and raw_recs:
        for r in raw_recs:
            if isinstance(r, dict):
                recs.append({
                    "title": str(r.get("title") or "Impulsa tu presencia digital").strip()[:200],
                    "description": str(r.get("description") or f"Comparte publicaciones de valor sobre {request.business.primary_product}.").strip()[:1000],
                    "priority": r.get("priority") if r.get("priority") in ("high", "medium", "low") else "high",
                })
    if not recs:
        recs = [{
            "title": "Publica con consistencia",
            "description": f"Destaca {request.business.primary_product} para conectar con {request.business.target_audience}.",
            "priority": "high",
        }]

    raw_actions = merged.get("next_actions")
    if isinstance(raw_actions, list) and raw_actions:
        next_actions = [str(a).strip()[:300] for a in raw_actions if str(a).strip()]
    else:
        next_actions = ["Crea un post promocional en Canva", "Planifica 3 publicaciones para esta semana"]

    result = {
        "summary": str(merged.get("summary") or f"Recomendación estratégica para {request.business.name}.").strip()[:1000],
        "recommendations": recs,
        "next_actions": next_actions,
    }
    if "__provider_metadata" in raw:
        result["__provider_metadata"] = raw["__provider_metadata"]
    return result


class ContentModelProvider(Protocol):
    provider_name: str
    model_name: str

    async def generate_advice(self, *, request: AdvisorModelRequest) -> dict: ...

    async def generate_social_post(
        self,
        *,
        request: SocialPostModelRequest,
    ) -> dict:
        """Return an untrusted provider payload to be validated by the application."""
        ...

    async def repair_social_post(
        self,
        *,
        request: SocialPostModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict: ...

    async def generate_short_video_script(self, *, request: ShortVideoScriptModelRequest) -> dict:
        """Return an untrusted provider payload to be validated by the application."""
        ...

    async def repair_short_video_script(
        self,
        *,
        request: ShortVideoScriptModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict: ...


def _extract_prompt_entities(user_request: str, default_biz: Any) -> tuple[str, str, str, bool]:
    text = user_request.strip()
    text_lower = text.lower()

    brand = getattr(default_biz, "name", "Tu Negocio")
    product = getattr(default_biz, "primary_product", "Servicios y Productos")
    category = getattr(default_biz, "category", "Comercio")
    wants_colors = bool(re.search(r"(?:color|esquema|paleta|tonos|hex|diseño)", text_lower))

    # 1. Look for brand after "llamada", "llamado", "marca", "nombre"
    m_brand = re.search(
        r"(?:llamada|llamado|marca|nombre)\s+([A-Za-z0-9áéíóúÁÉÍÓÚñÑ\s]+?)(?:,|\.|$|\s+dame|\s+con|\s+para|\s+y\s+)",
        text,
        re.IGNORECASE,
    )
    if m_brand:
        found_brand = m_brand.group(1).strip()
        if len(found_brand) >= 2:
            brand = found_brand.title()

    # 2. Look for product / niche
    m_prod = re.search(
        r"(?:empresa de|negocio de|diseño para mi empresa de|diseño para|post sobre|post de|para mi empresa de|sobre)\s+([A-Za-z0-9áéíóúÁÉÍÓÚñÑ\s]+?)(?:llamada|llamado|con|\.|\,|$|\s+dame|\s+en\s+)",
        text,
        re.IGNORECASE,
    )
    if m_prod:
        found_prod = m_prod.group(1).strip()
        if len(found_prod) >= 3 and not found_prod.lower().startswith("mi "):
            product = found_prod

    return brand, product, category, wants_colors


class DemoContentModelProvider:
    provider_name = "demo"
    model_name = "demo-v1"

    async def generate_advice(self, *, request: AdvisorModelRequest) -> dict:
        business = request.business
        brand, product, category, _ = _extract_prompt_entities(request.user_request, business)
        language = {
            "en": (
                "Focus on clear communication",
                "Highlight your value",
                "Connect",
                "Prepare a short post with a call to action.",
            ),
            "pt": (
                "Priorize uma comunicação clara",
                "Destaque sua proposta",
                "Conecte",
                "Prepare uma publicação breve com uma chamada para ação.",
            ),
        }.get(
            request.locale,
            (
                "Prioriza una comunicación clara",
                "Destaca tu propuesta",
                "Conecta",
                "Prepara una publicación breve con una llamada a la acción.",
            ),
        )
        forbidden = {word.casefold() for word in business.forbidden_words}
        preferred = next(
            (word for word in business.preferred_words if word.casefold() not in forbidden),
            None,
        )
        detail = f" {preferred}." if preferred else "."
        summary = {
            "en": f"{language[0]} for {brand}{detail}",
            "pt": f"{language[0]} para {brand}{detail}",
            "es": f"{language[0]} para {brand}{detail}",
        }[request.locale]
        description = {
            "en": f"{language[2]} {product} with {business.target_audience}{detail}",
            "pt": f"{language[2]} {product} com {business.target_audience}{detail}",
            "es": f"{language[2]} {product} con {business.target_audience}{detail}",
        }[request.locale]
        return {
            "summary": summary,
            "recommendations": [{"title": language[1], "description": description, "priority": "high"}],
            "next_actions": [language[3]],
        }

    @staticmethod
    def _call_to_action(objective: str, locale: str = "es") -> str:
        calls_to_action = {
            "es": {
                "reach": "Compártelo con alguien que disfrutaría conocerlo.",
                "engagement": "Cuéntanos qué te parece.",
                "sales": "Escríbenos para conocer la disponibilidad.",
                "store_visits": "Visítanos y conócelo en el local.",
                "launch": "Descúbrelo desde su lanzamiento.",
                "brand_awareness": "Síguenos para conocer más de nuestra propuesta.",
                "community": "Únete a la conversación y comparte tu experiencia.",
            },
            "en": {
                "reach": "Share it with someone who would love to discover it.",
                "engagement": "Tell us what you think.",
                "sales": "Message us to check availability.",
                "store_visits": "Visit us and discover it in person.",
                "launch": "Discover it from launch day.",
                "brand_awareness": "Follow us to learn more about our offer.",
                "community": "Join the conversation and share your experience.",
            },
            "pt": {
                "reach": "Compartilhe com alguém que gostaria de conhecer.",
                "engagement": "Conte para nós o que você acha.",
                "sales": "Envie uma mensagem para saber a disponibilidade.",
                "store_visits": "Visite-nos e conheça pessoalmente.",
                "launch": "Conheça desde o lançamento.",
                "brand_awareness": "Siga-nos para saber mais sobre nossa proposta.",
                "community": "Participe da conversa e compartilhe sua experiência.",
            },
        }
        return calls_to_action.get(locale, calls_to_action["es"])[objective]

    async def generate_social_post(
        self,
        *,
        request: SocialPostModelRequest,
    ) -> dict:
        context = request.business
        platform = request.platform
        tone = request.tone
        objective = request.objective
        text_lower = request.user_request.lower()
        cta = self._call_to_action(objective, request.locale)

        brand, product, category, wants_colors = _extract_prompt_entities(request.user_request, context)

        hook = f"Conoce {product} con {brand}"
        caption = (
            f"{brand} presenta {product}. "
            f"Una propuesta pensada para {context.target_audience.lower()} en {context.city}. {cta}"
        )
        visual = "Usa una imagen clara del producto, poco texto y una acción principal visible."
        forbidden = {f.casefold() for f in context.forbidden_words}
        preferred = next(
            (
                word for word in context.preferred_words
                if word.casefold() not in forbidden
            ),
            None,
        )

        if "más corto" in text_lower or "shorter" in text_lower:
            caption = (
                f"{product} de {brand}. "
                f"Pensado para ti en {context.city}. {cta}"
            )
            hook = f"{product} ✨"
            visual = "Imagen del producto con texto mínimo."

        if (
            "más juvenil" in text_lower
            or "more youthful" in text_lower
            or "more_youthful" in text_lower
        ):
            tone = "youthful"
            hook = f"Tu próximo favorito: {product} 🔥"
            caption = (
                f"Atención {context.target_audience.lower()} 🔥 "
                f"{brand} trae {product}. "
                f"{cta} No te lo pierdas."
            )

        if request.locale == "en":
            hook = f"Discover {product} with {brand}"
            caption = f"{brand} presents {product} for {context.target_audience.lower()}. {cta}"
            visual = "Use a clear product image with minimal text."
        elif request.locale == "pt":
            hook = f"Conheça {product} com {brand}"
            caption = f"{brand} apresenta {product} para {context.target_audience.lower()}. {cta}"
            visual = "Use uma imagem clara do produto com pouco texto."

        if preferred:
            caption = f"{caption} {preferred}"

        if (
            "más profesional" in text_lower
            or "more professional" in text_lower
            or "more_professional" in text_lower
        ):
            tone = "professional"
            if request.locale == "en":
                hook = f"{product} — {brand}"
                caption = f"{brand} presents {product}, thoughtfully selected for {context.target_audience.lower()} in {context.city}. {cta}"
            elif request.locale == "pt":
                hook = f"{product} — {brand}"
                caption = f"{brand} apresenta {product}, cuidadosamente selecionado para {context.target_audience.lower()} em {context.city}. {cta}"
            else:
                hook = f"{product} — {brand}"
                caption = f"{brand} presenta {product}. Una propuesta cuidadosamente seleccionada para {context.target_audience.lower()} en {context.city}. {cta}"

        if (
            "más amigable" in text_lower
            or "more friendly" in text_lower
            or "more_friendly" in text_lower
        ):
            tone = "friendly"
            if request.locale == "en":
                hook = "We have something special for you! 🎉"
                caption = f"Hi! {brand} has {product} you will love, made for {context.target_audience.lower()}. {cta}"
            elif request.locale == "pt":
                hook = "Temos algo especial para você! 🎉"
                caption = f"Olá! {brand} tem {product} que você vai adorar, pensado para {context.target_audience.lower()}. {cta}"
            else:
                hook = "¡Tenemos algo especial para ti! 🎉"
                caption = f"¡Hola! En {brand} tenemos {product} que te encantará. Está pensado para {context.target_audience.lower()} como tú. {cta} Te esperamos."

        if platform == "instagram":
            visual = {
                "en": f"4:5 vertical visual brief for Canva: centered {product}, clean editorial style, suggested text ‘{brand}’, generous margins and one clear action.",
                "pt": f"Brief visual vertical 4:5 para Canva: {product} centralizado, estilo editorial limpo, texto sugerido ‘{brand}’, margens generosas e uma ação clara.",
                "es": f"Brief visual vertical 4:5 para Canva: {product} centrado, estilo editorial limpio, texto sugerido ‘{brand}’, márgenes amplios y una acción clara.",
            }[request.locale]

        localized = {
            "en": ("#HiTrendy", "#BusinessContent", f"The {tone} tone from the profile or request was used."),
            "pt": ("#HiTrendy", "#ConteudoParaNegocios", f"Foi usado o tom {tone} do perfil ou da solicitação."),
            "es": ("#HiTrendy", "#ContenidoParaNegocios", f"Se utilizó el tono {tone} del perfil o la solicitud."),
        }[request.locale]

        return {
            "artifact_type": "social_post",
            "platform": platform,
            "hook": hook[:140],
            "caption": caption[:2200],
            "call_to_action": cta[:240],
            "hashtags": [localized[0], localized[1]],
            "visual_direction": visual[:700],
            "format_recommendation": "reel" if platform in {"instagram", "tiktok"} else "static_post",
            "assumptions": [localized[2]],
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
        context = request.business
        cta = self._call_to_action(request.objective, request.locale)
        product = context.primary_product
        return {
            "artifact_type": "short_video_script",
            "platform": request.platform,
            "hook": f"Así se vive {product} en {context.name}",
            "duration_seconds": 24,
            "scenes": [
                {
                    "order": 1,
                    "duration_seconds": 4,
                    "visual": f"Plano vertical cercano de {product} con luz natural.",
                    "on_screen_text": f"{product} en {context.name}",
                    "voiceover": f"¿Buscas una pausa diferente? Conoce {product}.",
                },
                {
                    "order": 2,
                    "duration_seconds": 10,
                    "visual": "Muestra el detalle más atractivo mientras una persona lo disfruta.",
                    "on_screen_text": "Hecho para disfrutar el momento",
                    "voiceover": (
                        f"En {context.name} lo pensamos para {context.target_audience.lower()}."
                    ),
                },
                {
                    "order": 3,
                    "duration_seconds": 10,
                    "visual": "Cierra con el producto y una toma simple del negocio o su empaque.",
                    "on_screen_text": "Conócelo hoy",
                    "voiceover": cta,
                },
            ],
            "call_to_action": cta,
            "caption": (
                f"Conoce {product} de {context.name}. "
                f"Una propuesta para {context.target_audience.lower()}. {cta}"
            ),
            "assumptions": [
                f"Se utilizó el tono {request.tone} y el objetivo {request.objective} del perfil."
            ],
        }

    async def repair_short_video_script(
        self,
        *,
        request: ShortVideoScriptModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict:
        return await self.generate_short_video_script(request=request)


class OpenAICompatibleContentModelProvider:
    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float = 30,
        max_retries: int = 1,
        retry_base_seconds: float = 0.5,
        http_referer: str = "",
        app_title: str = "HiTrendy",
        provider_name: str = "openai-compatible",
        structured_output: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.provider_name = provider_name
        self.model_name = model_name
        self._timeout = httpx.Timeout(timeout_seconds)
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._http_referer = http_referer
        self._app_title = app_title
        self._transport = transport
        self._sleep = sleep
        self._structured_output = structured_output

    async def generate_social_post(self, *, request: SocialPostModelRequest) -> dict:
        system_prompt, _ = get_social_copy_prompt()
        raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(request.model_dump(), ensure_ascii=False)},
            ],
            response_schema=GeneratedSocialPost.model_json_schema(),
        )
        return _normalize_social_post_payload(raw, request)

    async def fetch_model_catalog(self) -> list[object]:
        """Fetch OpenAI-compatible model data through this adapter's auth/client setup."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
                response = await client.get(f"{self._base_url}/models", headers=self._headers())
            response.raise_for_status()
            envelope = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ValueError("Catálogo remoto no disponible.") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("data"), list):
            raise ValueError("Catálogo remoto inválido.")
        return envelope["data"]

    async def generate_advice(self, *, request: AdvisorModelRequest) -> dict:
        system = (
            "Devuelve únicamente JSON válido con summary, recommendations y next_actions. "
            "No incluyas razonamiento privado. Respeta el locale y evita las palabras prohibidas del perfil."
        )
        raw = await self._complete(
            messages=[{"role": "system", "content": system}, {"role": "user", "content": json.dumps(request.model_dump(), ensure_ascii=False)}],
            response_schema=AdvisorResponse.model_json_schema(),
        )
        return _normalize_advice_payload(raw, request)

    async def repair_social_post(
        self,
        *,
        request: SocialPostModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict:
        system_prompt, _ = get_social_copy_prompt()
        repair = {
            "request": request.model_dump(),
            "invalid_output": invalid_output,
            "validation_errors": errors,
            "instruction": "Corrige sólo lo necesario y devuelve únicamente el JSON del schema.",
        }
        raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(repair, ensure_ascii=False)},
            ],
            response_schema=GeneratedSocialPost.model_json_schema(),
        )
        return _normalize_social_post_payload(raw, request)

    async def generate_short_video_script(self, *, request: ShortVideoScriptModelRequest) -> dict:
        system_prompt, _ = get_short_video_script_prompt()
        raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(request.model_dump(), ensure_ascii=False)},
            ]
        )
        return _normalize_video_script_payload(raw, request)

    async def repair_short_video_script(
        self,
        *,
        request: ShortVideoScriptModelRequest,
        invalid_output: dict,
        errors: list[str],
    ) -> dict:
        system_prompt, _ = get_short_video_script_prompt()
        repair = {
            "request": request.model_dump(),
            "invalid_output": invalid_output,
            "validation_errors": errors,
            "instruction": "Corrige sólo lo necesario y devuelve únicamente el JSON del schema.",
        }
        raw = await self._complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(repair, ensure_ascii=False)},
            ]
        )
        return _normalize_video_script_payload(raw, request)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._http_referer:
            headers["HTTP-Referer"] = self._http_referer
        if self._app_title:
            headers["X-Title"] = self._app_title
        return headers

    async def _complete(
        self, *, messages: list[dict[str, str]], response_schema: dict[str, Any] | None = None
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "response_format": self._response_format(response_schema),
        }
        # Reasoning models (gpt-5, o1, o3, o4) reject any temperature other than
        # their default of 1 with an HTTP 400, which would fail every generation
        # instead of degrading. Sampling is not configurable on them, so the
        # sensible request is the one that omits the parameter entirely.
        if not _rejects_temperature(self.model_name):
            payload["temperature"] = 0.4

        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        f"{self._base_url}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException as exc:
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise AppError(
                    "GENERATION_PROVIDER_TIMEOUT",
                    "La generación tardó demasiado. Inténtalo de nuevo.",
                    status_code=504,
                    retryable=True,
                ) from exc
            except httpx.RequestError as exc:
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise AppError(
                    "GENERATION_PROVIDER_UNAVAILABLE",
                    "No pudimos conectar con el servicio de generación. Inténtalo de nuevo.",
                    status_code=503,
                    retryable=True,
                ) from exc

            if response.status_code == 402:
                raise AppError(
                    "PAYMENT_REQUIRED",
                    "Esta ruta de generación requiere presupuesto habilitado.",
                    status_code=402,
                    retryable=False,
                )

            if response.status_code == 429:
                quota_exhausted = self._is_quota_exhausted(response)
                retry_after = self._retry_after(response)
                if quota_exhausted:
                    raise AppError(
                        "GENERATION_PROVIDER_QUOTA_EXHAUSTED",
                        "La cuota disponible para esta generación se agotó.",
                        status_code=429,
                        retryable=False,
                        retry_after=retry_after,
                    )
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                message = "El servicio de generación está ocupado. Inténtalo de nuevo en un momento."
                if retry_after is not None:
                    message = f"El servicio de generación está ocupado. Inténtalo nuevamente en {retry_after} segundos."
                raise AppError(
                    "GENERATION_PROVIDER_RATE_LIMITED",
                    message,
                    status_code=429,
                    retryable=True,
                    retry_after=retry_after,
                )

            if 500 <= response.status_code <= 599:
                if attempt < self._max_retries:
                    await self._backoff(attempt)
                    continue
                raise AppError(
                    "GENERATION_PROVIDER_UNAVAILABLE",
                    "El servicio de generación no está disponible en este momento.",
                    status_code=503,
                    retryable=True,
                )

            if response.status_code >= 400:
                raise AppError(
                    "GENERATION_PROVIDER_REJECTED",
                    "El servicio de generación rechazó la solicitud.",
                    status_code=502,
                    retryable=False,
                )

            return self._decode_response(response)

        raise AppError(
            "GENERATION_PROVIDER_UNAVAILABLE",
            "El servicio de generación no está disponible en este momento.",
            status_code=503,
            retryable=True,
        )

    async def _backoff(self, attempt: int) -> None:
        delay = self._retry_base_seconds * (2**attempt)
        await self._sleep(delay)

    def _response_format(self, response_schema: dict[str, Any] | None) -> dict[str, Any]:
        if self._structured_output and response_schema is not None:
            return {
                "type": "json_schema",
                "json_schema": {
                    "name": "hitrendy_response",
                    "strict": True,
                    "schema": _to_strict_schema(response_schema),
                },
            }
        return {"type": "json_object"}

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        value = response.headers.get("Retry-After", "").strip()
        if value.isdigit():
            parsed = int(value)
            return parsed if 1 <= parsed <= 86400 else None
        return None

    @staticmethod
    def _is_quota_exhausted(response: httpx.Response) -> bool:
        """Classify only explicit quota/credit signals; ordinary 429 stays rate limited."""
        try:
            body = response.json()
        except ValueError:
            return False
        if not isinstance(body, dict):
            return False
        error = body.get("error", body)
        if not isinstance(error, dict):
            return False
        signal = " ".join(
            str(error.get(key, "")) for key in ("code", "type", "message")
        ).casefold()
        return any(term in signal for term in ("quota", "credit", "insufficient", "exhausted"))

    def _decode_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            envelope = response.json()
        except ValueError as exc:
            raise AppError(
                "GENERATION_PROVIDER_INVALID_RESPONSE",
                "El servicio devolvió una respuesta que no pudimos procesar.",
                status_code=502,
                retryable=True,
            ) from exc

        if not isinstance(envelope, dict):
            raise AppError(
                "GENERATION_PROVIDER_INVALID_RESPONSE",
                "El servicio devolvió una respuesta que no pudimos procesar.",
                status_code=502,
                retryable=True,
            )

        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise AppError(
                "GENERATION_PROVIDER_INVALID_RESPONSE",
                "El servicio devolvió una respuesta que no pudimos procesar.",
                status_code=502,
                retryable=True,
            )

        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise AppError(
                "GENERATION_PROVIDER_INVALID_RESPONSE",
                "El servicio devolvió una respuesta que no pudimos procesar.",
                status_code=502,
                retryable=True,
            )

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise AppError(
                "GENERATION_PROVIDER_INVALID_RESPONSE",
                "El servicio devolvió una respuesta que no pudimos procesar.",
                status_code=502,
                retryable=True,
            )

        clean_content = content.strip()
        if clean_content.startswith("```"):
            lines = clean_content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            clean_content = "\n".join(lines).strip()

        parsed: Any = None
        try:
            parsed = json.loads(clean_content)
        except json.JSONDecodeError:
            if "{" in clean_content and "}" in clean_content:
                start = clean_content.find("{")
                end = clean_content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    try:
                        parsed = json.loads(clean_content[start : end + 1])
                    except json.JSONDecodeError as nested_exc:
                        raise AppError(
                            "GENERATION_PROVIDER_INVALID_RESPONSE",
                            "El servicio devolvió una respuesta que no pudimos procesar.",
                            status_code=502,
                            retryable=True,
                        ) from nested_exc
            if parsed is None:
                raise AppError(
                    "GENERATION_PROVIDER_INVALID_RESPONSE",
                    "El servicio devolvió una respuesta que no pudimos procesar.",
                    status_code=502,
                    retryable=True,
                )

        if not isinstance(parsed, dict):
            raise AppError(
                "GENERATION_PROVIDER_INVALID_RESPONSE",
                "El servicio devolvió una respuesta que no pudimos procesar.",
                status_code=502,
                retryable=True,
            )
        usage = envelope.get("usage")
        if self.provider_name != "openrouter":
            return parsed
        metadata: dict[str, Any] = {
            "requested_model": self.model_name,
            "actual_model": envelope.get("model") if isinstance(envelope.get("model"), str) else None,
            "prompt_tokens": usage.get("prompt_tokens") if isinstance(usage, dict) else None,
            "completion_tokens": usage.get("completion_tokens") if isinstance(usage, dict) else None,
            "total_tokens": usage.get("total_tokens") if isinstance(usage, dict) else None,
            "reported_cost": usage.get("cost") if isinstance(usage, dict) else None,
            "currency": "USD" if isinstance(usage, dict) and usage.get("cost") is not None else None,
            "provider_request_id": envelope.get("id") if isinstance(envelope.get("id"), str) else None,
        }
        return {**parsed, "__provider_metadata": metadata}
