"""The editable visual brief and the prompt composed from it.

The brief is the only thing a user edits. It is a bounded, database-free
structure: the server proposes a draft from the business profile and the
publication, the user corrects it, and the confirmed brief becomes the prompt.

What never crosses this boundary: workspace IDs, business IDs, asset IDs, user
names, emails and any other tenant identifier. The provider receives a
description of the image, not a description of the account.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from app.core.errors import ValidationError_
from app.domain.models import BusinessGenerationContext
from app.providers.images import ASPECT_RATIOS

#: Field ceilings. They bound both what a user may type and what the composed
#: prompt can grow to, so a client cannot inflate a paid request.
FIELD_LIMITS: dict[str, int] = {
    "subject": 240,
    "setting": 240,
    "style": 200,
    "palette": 160,
    "mood": 120,
    "avoid": 240,
}

MAX_PROMPT_CHARS = 1800

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")

#: Text a user could paste to try to redirect the provider away from the brief.
_INJECTION_MARKERS = (
    "ignore previous",
    "ignora las instrucciones",
    "system:",
    "assistant:",
    "<|",
)


def sanitize_field(value: str | None, *, field: str) -> str:
    """Normalize one brief field to bounded, single-line, printable text."""

    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    limit = FIELD_LIMITS[field]
    if len(text) > limit:
        raise ValidationError_(f"El campo del brief supera {limit} caracteres.")
    lowered = text.casefold()
    for marker in _INJECTION_MARKERS:
        if marker in lowered:
            raise ValidationError_("El brief contiene instrucciones no permitidas.")
    return text


@dataclass(frozen=True)
class VisualBrief:
    """What the image should show. Editable by the user, bounded by the server."""

    subject: str
    setting: str
    style: str
    palette: str
    mood: str
    avoid: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def normalize_brief(payload: dict[str, Any] | None) -> VisualBrief:
    """Build a validated brief from untrusted input."""

    data = payload or {}
    if not isinstance(data, dict):
        raise ValidationError_("El brief visual no es válido.")
    brief = VisualBrief(
        subject=sanitize_field(data.get("subject"), field="subject"),
        setting=sanitize_field(data.get("setting"), field="setting"),
        style=sanitize_field(data.get("style"), field="style"),
        palette=sanitize_field(data.get("palette"), field="palette"),
        mood=sanitize_field(data.get("mood"), field="mood"),
        avoid=sanitize_field(data.get("avoid"), field="avoid"),
    )
    if not brief.subject:
        raise ValidationError_("Describe qué debe mostrar la imagen.")
    return brief


def normalize_aspect_ratio(value: str | None) -> str:
    """Accept only the three published formats."""

    candidate = (value or "").strip()
    if candidate not in ASPECT_RATIOS:
        raise ValidationError_("El formato solicitado no está disponible.")
    return candidate


def draft_brief(
    *,
    context: BusinessGenerationContext,
    publication_text: str | None = None,
    trend_title: str | None = None,
) -> VisualBrief:
    """Propose an editable draft from the business profile and the publication.

    Everything here is descriptive: the product, the audience and the brand
    tones shape the image, while identifiers stay behind.
    """

    subject_source = publication_text or trend_title or context.primary_product
    subject = _first_sentence(subject_source) or context.primary_product
    tones = ", ".join(_tone_label(tone) for tone in context.brand_tones[:3])
    return VisualBrief(
        subject=sanitize_field(subject, field="subject"),
        setting=sanitize_field(
            f"Ambiente de {context.category} en {context.city}", field="setting"
        ),
        style=sanitize_field(
            "Fotografía de producto, luz natural, encuadre limpio", field="style"
        ),
        palette=sanitize_field("Colores cálidos y coherentes con la marca", field="palette"),
        mood=sanitize_field(tones or "cercano", field="mood"),
        avoid=sanitize_field(
            "Texto ilegible, logotipos de terceros, rostros reconocibles", field="avoid"
        ),
    )


def _tone_label(tone: Any) -> str:
    return tone.value if hasattr(tone, "value") else str(tone)


def _first_sentence(text: str | None) -> str:
    if not text:
        return ""
    cleaned = _WHITESPACE.sub(" ", _CONTROL.sub(" ", text)).strip()
    for separator in (". ", "\n", " · "):
        head, found, _ = cleaned.partition(separator)
        if found:
            cleaned = head
            break
    return cleaned[: FIELD_LIMITS["subject"]].strip()


def compose_prompt(brief: VisualBrief, *, aspect_ratio: str) -> str:
    """Render the confirmed brief as the single prompt string sent upstream."""

    parts = [f"Imagen para redes sociales en formato {aspect_ratio}.", brief.subject]
    for label, value in (
        ("Entorno", brief.setting),
        ("Estilo", brief.style),
        ("Paleta", brief.palette),
        ("Ánimo", brief.mood),
    ):
        if value:
            parts.append(f"{label}: {value}.")
    parts.append("Sin texto superpuesto ni marcas de agua.")
    prompt = " ".join(part for part in parts if part).strip()
    return prompt[:MAX_PROMPT_CHARS]


def compose_negative_prompt(brief: VisualBrief) -> str | None:
    """Return what to avoid, or ``None`` when the user left it empty."""

    if not brief.avoid:
        return None
    return brief.avoid[: FIELD_LIMITS["avoid"]]
