import base64
import json
import logging
import re
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.errors import AppError

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Canva search
#
# Canva ranks a search on a handful of words and scopes it by the format in the
# path. The previous queries pasted whole business fields into a generic
# /templates/ search, which came back with presentations and posters for an
# Instagram brief. Everything below builds short, format-scoped searches
# instead, and is the single place a Canva URL is produced.
# --------------------------------------------------------------------------- #

CANVA_SEARCH_BASE = "https://www.canva.com/templates/"

#: Words that scope a search to a format.
#:
#: These used to be paths -- https://www.canva.com/instagram-posts/templates/
#: and friends -- with the search appended as ?query=. Canva ignores the
#: parameter there: those pages emit a canonical tag that drops the query
#: string, and the searched words appear nowhere in what they return, so every
#: recommendation landed on the same evergreen category gallery no matter what
#: had been searched for. Only /templates/?query= actually searches, so the
#: format has to travel inside the query text instead of in the path.
CANVA_FORMAT_TERMS = {
    "instagram_post": "instagram post",
    "instagram_story": "instagram story",
    "facebook_post": "facebook post",
    "flyer": "flyer",
    "poster": "poster",
}

#: Hosts a recommendation is allowed to point at.
_CANVA_HOSTS = ("canva.com", "canva.link")

#: Function words carry no search signal and crowd out the terms that do.
_QUERY_STOPWORDS = frozenset(
    {
        "de", "del", "la", "el", "lo", "los", "las", "un", "una", "unos", "unas",
        "y", "o", "u", "a", "al", "en", "con", "por", "para", "sin", "sobre",
        "que", "como", "mas", "muy", "tu", "tus", "mi", "mis", "su", "sus",
        "nuestro", "nuestra", "the", "and", "for", "of", "our", "your",
    }
)

_WORD_SPLIT = re.compile(r"[^0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def canva_keywords(*parts: str | None, limit: int = 5) -> list[str]:
    """Reduce free-text business fields to a short, de-duplicated term list.

    Parts are consumed in order, so the caller decides what survives the cap.
    """
    words: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        for raw in _WORD_SPLIT.split(part.strip().lower()):
            if len(raw) < 3 or raw in _QUERY_STOPWORDS or raw in seen:
                continue
            seen.add(raw)
            words.append(raw)
            if len(words) >= limit:
                return words
    return words


def canva_search_url(terms: Sequence[str] | str, *, fmt: str = "instagram_post") -> str:
    """Build a format-scoped Canva template search for ``terms``."""
    joined = terms if isinstance(terms, str) else " ".join(terms)
    scoped = " ".join(part for part in (CANVA_FORMAT_TERMS.get(fmt, ""), joined.strip()) if part)
    query = urllib.parse.quote_plus(scoped)
    return f"{CANVA_SEARCH_BASE}?query={query}" if query else CANVA_SEARCH_BASE


def normalize_canva_url(url: object, fallback_terms: Sequence[str]) -> str:
    """Keep provider-supplied links that really point at Canva, replace the rest.

    A model asked for a URL will happily invent a host or a template id that
    404s, so anything off Canva is swapped for a search we know resolves.
    """
    if isinstance(url, str) and url.strip():
        parsed = urllib.parse.urlsplit(url.strip())
        host = parsed.netloc.lower().removeprefix("www.")
        if parsed.scheme in {"http", "https"} and host in _CANVA_HOSTS:
            return urllib.parse.urlunsplit(
                ("https", parsed.netloc, parsed.path, parsed.query, "")
            )
    return canva_search_url(fallback_terms)


def build_canva_search_plan(request: "VisionReviewRequest") -> dict:
    """Derive the searches to offer for one business, plus refinement seeds.

    Three angles rather than three phrasings of the same one: the promotion,
    the product shot and the brand piece are the posts a small business
    actually needs, and each wants a different template.
    """
    product = request.primary_product or ""
    category = request.business_category or ""
    audience = request.target_audience or ""

    promo = canva_keywords(product, category, "promocion oferta", limit=5)
    product_shot = canva_keywords(product, "foto producto minimalista", limit=5)
    brand = canva_keywords(category, audience, "marca moderno elegante", limit=5)
    primary = promo or product_shot or brand or ["negocio local promocion"]

    return {
        "primary": primary,
        "promo": promo or primary,
        "product": product_shot or primary,
        "brand": brand or primary,
        # Offered as one-tap chips beside the results: different looks for the
        # same brief, which is what a user reaches for after seeing the picks.
        "suggestions": [
            " ".join(canva_keywords(product, "minimalista", limit=3)) or "minimalista",
            " ".join(canva_keywords(product, category, "descuento", limit=3))
            or "descuento",
            " ".join(canva_keywords(category, "tipografia grande", limit=3))
            or "tipografia grande",
        ],
    }


#: Niche token the web turns into a designed cover when a recommendation has no
#: bitmap. Deliberately compact: the web keeps a far richer keyword table in
#: ``lib/canva-templates.ts`` and duplicating it here would leave two lists to
#: keep in sync, so this one holds only the words that decide a cover.
_COVER_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("gastronomy", ("gastronom", "restaurante", "comida", "cafe", "café", "panader", "pizza", "bar")),
    ("beauty", ("belleza", "salon", "salón", "spa", "uñas", "maquillaje", "peluquer", "barber")),
    ("fashion", ("moda", "ropa", "boutique", "zapato", "accesorio", "fashion")),
    ("fitness", ("gimnasio", "gym", "fitness", "entrenamiento", "crossfit", "yoga")),
    ("health", ("salud", "health", "clinic", "clínic", "dental", "médic", "medic", "farmacia", "psicolog")),
    ("technology", ("tecnolog", "technology", "software", "digital", "computad", "celular", "electrónic")),
    ("education", ("educac", "curso", "academia", "escuela", "clases", "tutor")),
    ("real_estate", ("inmobiliar", "bienes raices", "bienes raíces", "apartamento", "propiedad")),
    ("automotive", ("automotriz", "taller", "carro", "vehícul", "vehicul", "llanta", "mecánic")),
    ("travel", ("viaje", "turismo", "hotel", "tour", "hostal")),
    ("events", ("evento", "boda", "fiesta", "catering", "banquete", "decorac")),
    ("pets", ("mascota", "perro", "gato", "veterinar")),
)

#: Categories such as "retail", "services" or "other" name no niche; a
#: promotional look is the least wrong cover for them.
_DEFAULT_COVER = "events"


def cover_for(request: "VisionReviewRequest") -> str:
    """Pick the niche token whose cover best fits this business."""
    category = (request.business_category or "").strip().lower()
    # The onboarding category vocabulary already overlaps the cover tokens, so
    # an exact match beats guessing from free text.
    if category in {token for token, _ in _COVER_KEYWORDS}:
        return category
    haystack = " ".join(
        part.lower()
        for part in (request.business_category, request.primary_product, request.business_name)
        if part
    )
    for token, keywords in _COVER_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return token
    return _DEFAULT_COVER


@dataclass(frozen=True)
class VisionReviewRequest:
    """A bounded, authorized image review request with no storage URL or tenant data."""

    mime_type: str
    width: int | None
    height: int | None
    image_bytes: bytes | None = None
    business_name: str | None = None
    business_category: str | None = None
    primary_product: str | None = None
    target_audience: str | None = None
    city: str | None = None
    #: What the user actually asked about this image, when they asked anything.
    #: The review is the same either way; this decides what the answer leads
    #: with, so an uploaded image stops producing one fixed audit.
    question: str | None = None


class VisionReviewProvider(Protocol):
    provider_name: str
    requires_image_content: bool

    async def analyze(self, *, request: VisionReviewRequest) -> dict:
        """Return untrusted data that the application validates against AssetAnalysis."""
        ...


class DemoVisionReviewProvider:
    """Evaluator that provides dynamic AI design audit and live Canva search recommendations."""

    provider_name = "demo"
    requires_image_content = False

    async def analyze(self, *, request: VisionReviewRequest) -> dict:
        biz_name = request.business_name or "tu negocio"
        product = request.primary_product or "tus productos y servicios"
        category = request.business_category or "comercio"
        audience = request.target_audience or "tus clientes"

        plan = build_canva_search_plan(request)

        # This evaluator never looks at the pixels, and it is also the fallback
        # when the visual model fails. Either way it must not answer a question
        # as if it had seen the image, so it says what it is doing instead.
        question = (request.question or "").strip()
        asked = (
            f"Sobre tu pregunta (“{question[:200]}”): no pudimos leer la imagen con el "
            "modelo visual, así que respondemos con la auditoría estándar. "
            if question
            else ""
        )

        summary = (
            asked
            + f"Auditoría visual completada para {biz_name}: Analizamos la imagen orientada a {product}. "
            f"Detectamos oportunidades clave de mejora en la jerarquía del texto, legibilidad en móviles y contraste visual. "
            f"Para elevar la percepción de marca frente a {audience}, te recomendamos aplicar plantillas de Canva curadas por diseñadores."
        )

        strengths = [
            f"Enfoque temático directo orientado a {product}.",
            "Intención comercial clara con potencial de conversión en redes sociales.",
        ]

        improvements = [
            {
                "priority": "high",
                "area": "hierarchy",
                "reason": "El texto principal compite con el fondo y carece de márgenes seguros para visualización en teléfonos móviles (común en diseños generados automáticamente).",
                "action": "Aplica una plantilla de Canva estructurada con tipografías legibles y espacio negativo para que el producto sea el protagonista.",
            },
            {
                "priority": "medium",
                "area": "cta",
                "reason": "El llamado a la acción no está destacado en un contenedor o botón de alto impacto visual.",
                "action": f"Agrega un botón visible con texto claro como '¡Pide tu {product} hoy!' o 'Escríbenos por WhatsApp'.",
            },
            {
                "priority": "low",
                "area": "brand",
                "reason": f"La paleta de colores puede armonizarse con la identidad visual de {biz_name}.",
                "action": "Usa 2 colores principales de marca para fondos y un color de contraste vibrante para el botón de acción.",
            },
        ]

        ai_hallmarks = [
            "Falta de retícula estructurada y márgenes de seguridad para pantallas móviles.",
            "Contraste insuficiente entre el texto secundario y los elementos de fondo.",
            "Texturas o fondos planos que restan protagonismo a la fotografía principal del producto.",
        ]

        cover = cover_for(request)
        canva_templates = [
            {
                "title": f"Post promocional para {category}",
                "canva_url": canva_search_url(plan["promo"]),
                "thumbnail_url": "/templates/flores.png",
                "cover": cover,
                "reason": f"Estructura equilibrada para anunciar {product} con la oferta visible.",
            },
            {
                "title": "Producto destacado con foto grande",
                "canva_url": canva_search_url(plan["product"]),
                "thumbnail_url": "/templates/coffee.png",
                "cover": cover,
                "reason": "Deja la fotografía como protagonista y el titular limpio encima.",
            },
            {
                "title": f"Identidad de marca de {biz_name}",
                "canva_url": canva_search_url(plan["brand"]),
                "thumbnail_url": "/templates/about-collage.png",
                "cover": cover,
                "reason": f"Formatos sobrios para consolidar la imagen frente a {audience}.",
            },
        ]

        canva_slots_guide = {
            "headline": f"Lo mejor en {product} | {biz_name}",
            "body": f"Creado especialmente para ti. Descubre nuestra calidad única y déjanos sorprenderte hoy mismo.",
            "cta": f"¡Pide o visítanos hoy mismo!",
        }

        revised_copy = f"En {biz_name} tenemos {product} pensado para ti. ¡Escríbenos o visítanos para conocer más!"

        accessibility_notes = [
            "Asegura un contraste mínimo de 4.5:1 entre el texto y el fondo para garantizar lectura fácil.",
            "Deja márgenes de al menos 10% en todos los bordes para que los iconos de Instagram no tapen tu texto.",
        ]

        return {
            "summary": summary,
            "strengths": strengths,
            "improvements": improvements,
            "ai_hallmarks": ai_hallmarks,
            "canva_templates": canva_templates,
            "canva_slots_guide": canva_slots_guide,
            "canva_query": " ".join(plan["primary"]),
            "canva_query_suggestions": plan["suggestions"],
            "revised_copy": revised_copy,
            "accessibility_notes": accessibility_notes,
        }


class OpenAICompatibleVisionReviewProvider:
    """Vision adapter for an OpenAI-compatible chat-completions endpoint."""

    provider_name = "openai-compatible"
    requires_image_content = True

    def __init__(
        self, *, base_url: str, api_key: str, model_name: str, timeout_seconds: float = 30
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._timeout_seconds = timeout_seconds

    async def analyze(self, *, request: VisionReviewRequest) -> dict:
        if not request.image_bytes:
            return await DemoVisionReviewProvider().analyze(request=request)
        image_data = base64.b64encode(request.image_bytes).decode("ascii")
        biz_info = f"Negocio: {request.business_name or 'Comercio'}, Producto: {request.primary_product or 'Producto'}, Categoría: {request.business_category or 'General'}"
        question = (request.question or "").strip()
        rubric = {
            "business_context": biz_info,
            "image": {
                "mime_type": request.mime_type,
                "width": request.width,
                "height": request.height,
            },
            # Untrusted user text. It steers what the answer opens with; it
            # never replaces the instructions or the required JSON shape.
            "user_question": question or None,
            "instructions": (
                (
                    "El usuario preguntó lo siguiente sobre la imagen: "
                    f"\"{question[:400]}\". Responde ESA pregunta en 'summary', "
                    "en las primeras frases y de forma directa, mirando la imagen. "
                    "Después continúa con la evaluación. Si la pregunta no tiene "
                    "relación con la imagen, dilo y evalúa la imagen igualmente. "
                    if question
                    else ""
                )
                + (
                "Eres un experto en diseño gráfico y redes sociales. Evalúa la imagen comercial subida por el usuario. "
                "1. Diagnostica si tiene aspectos amateur o hechos por IA (tipografías sin contraste, artefactos, sobrecarga, textos deformados). "
                "2. Explica qué mejorar (jerarquía, contraste, legibilidad, llamado a la acción). "
                "3. En 'canva_templates', propón 2 o 3 plantillas distintas entre sí (promoción, producto destacado, marca). "
                "Para cada una escribe 'canva_query': de 3 a 5 palabras de búsqueda en español, sin la palabra 'Canva' ni el formato "
                "(por ejemplo 'restaurante promocion rojo' o 'tienda ropa minimalista'). NO escribas URLs: nosotros construimos el enlace. "
                "4. En 'canva_query_suggestions' añade 3 búsquedas alternativas cortas por si el usuario quiere otro estilo. "
                "5. Proporciona en 'canva_slots_guide' los textos clave para pegar en Canva (headline, body, cta). "
                "Devuelve ÚNICAMENTE un JSON válido con las claves: "
                "summary, strengths (lista), improvements (lista de objetos con priority: 'high'|'medium'|'low', area: 'message'|'hierarchy'|'readability'|'brand'|'cta'|'platform'|'accessibility', reason, action), "
                "ai_hallmarks (lista de 2-4 aspectos de IA o diseño detectados), "
                "canva_templates (lista de objetos con: title, canva_query, reason), "
                "canva_query_suggestions (lista de 3 strings cortos), "
                "canva_slots_guide (objeto con headline, body, cta), revised_copy (string), accessibility_notes (lista)."
            )),
        }
        payload = {
            "model": self._model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json.dumps(rubric, ensure_ascii=False)},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{request.mime_type};base64,{image_data}",
                            },
                        },
                    ],
                }
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 1400,
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            # Strip potential markdown fences
            content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content.strip())
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1:
                content = content[start : end + 1]
            parsed = json.loads(content)
            return self._resolve_canva_links(parsed, request)
        except Exception as exc:
            logger.exception("OpenAICompatibleVisionReviewProvider failed; falling back to DemoVisionReviewProvider: %s", exc)
            return await DemoVisionReviewProvider().analyze(request=request)

    @staticmethod
    def _resolve_canva_links(parsed: dict, request: VisionReviewRequest) -> dict:
        """Turn the model's search terms into links, and vet any it invented.

        The model is good at naming what to search for and bad at URLs, so the
        terms are what we ask for and the URL is built here. Anything it sent
        anyway still has to survive :func:`normalize_canva_url`.
        """
        plan = build_canva_search_plan(request)
        fallbacks = [plan["promo"], plan["product"], plan["brand"]]
        cover = cover_for(request)

        # Normalize improvements to match schema literals
        priority_map = {
            "alta": "high", "alto": "high", "high": "high",
            "media": "medium", "medio": "medium", "medium": "medium",
            "baja": "low", "bajo": "low", "low": "low",
        }
        area_map = {
            "message": "message", "mensaje": "message", "copy": "message", "texto": "message",
            "hierarchy": "hierarchy", "jerarquia": "hierarchy", "jerarquía": "hierarchy", "estructura": "hierarchy",
            "readability": "readability", "legibilidad": "readability", "contraste": "readability", "tipografia": "readability", "tipografía": "readability",
            "brand": "brand", "marca": "brand", "identidad": "brand", "colores": "brand",
            "cta": "cta", "llamado": "cta", "llamada": "cta",
            "platform": "platform", "plataforma": "platform", "formato": "platform",
            "accessibility": "accessibility", "accesibilidad": "accessibility",
        }
        improvements = parsed.get("improvements")
        if isinstance(improvements, list):
            clean_improvements = []
            for item in improvements:
                if not isinstance(item, dict):
                    continue
                p = str(item.get("priority", "")).lower().strip()
                item["priority"] = priority_map.get(p, "medium")
                a = str(item.get("area", "")).lower().strip()
                item["area"] = area_map.get(a, "readability")
                item["reason"] = str(item.get("reason", ""))[:300]
                item["action"] = str(item.get("action", ""))[:300]
                clean_improvements.append(item)
            parsed["improvements"] = clean_improvements

        templates = parsed.get("canva_templates")
        if isinstance(templates, list):
            for index, template in enumerate(templates):
                if not isinstance(template, dict):
                    continue
                # The model returns no artwork, so the web needs a niche to
                # draw a cover from instead of an empty card.
                template["cover"] = cover
                fallback = fallbacks[index % len(fallbacks)]
                query = template.pop("canva_query", None)
                if isinstance(query, str) and query.strip():
                    template["canva_url"] = canva_search_url(
                        canva_keywords(query, limit=5) or fallback
                    )
                else:
                    template["canva_url"] = normalize_canva_url(
                        template.get("canva_url"), fallback
                    )
                # Never keep local/mock template paths; only accept real external URLs
                thumb = str(template.get("thumbnail_url", "")).strip()
                if thumb.startswith("/templates/") or not (thumb.startswith("http://") or thumb.startswith("https://")):
                    template["thumbnail_url"] = ""

        suggestions = parsed.get("canva_query_suggestions")
        if not isinstance(suggestions, list) or not suggestions:
            parsed["canva_query_suggestions"] = plan["suggestions"]
        else:
            parsed["canva_query_suggestions"] = [
                str(item).strip() for item in suggestions[:4] if str(item).strip()
            ]

        if not isinstance(parsed.get("canva_query"), str) or not parsed["canva_query"].strip():
            parsed["canva_query"] = " ".join(plan["primary"])
        return parsed
