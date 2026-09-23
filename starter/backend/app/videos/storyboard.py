"""Deterministic, editable video storyboard fallback."""

from __future__ import annotations

import re
import unicodedata

from app.domain.models import BusinessGenerationContext
from app.videos.schemas import VideoShot, VideoStoryboard

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_WHITESPACE = re.compile(r"\s+")


def _clean(value: object, limit: int) -> str:
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()[:limit]


def _tone_label(tone: object) -> str:
    return _clean(getattr(tone, "value", tone), 40)


def _duration_parts(total: int, count: int) -> list[int]:
    if total < 1 or count < 1:
        raise ValueError("La duración y el número de tomas deben ser positivos.")
    count = min(count, total)
    base, remainder = divmod(total, count)
    return [base] * (count - 1) + [base + remainder]


def draft_storyboard(
    *,
    context: BusinessGenerationContext,
    publication_text: str | None,
    trend_title: str | None,
    duration_seconds: int,
) -> VideoStoryboard:
    """Build a useful script from approved business context without calling AI."""

    product = _clean(context.primary_product, 100) or "la propuesta del negocio"
    business_name = _clean(context.name, 100) or "el negocio"
    audience = _clean(context.target_audience, 100) or "tu audiencia"
    category = _clean(context.category, 80) or "el negocio"
    publication = _clean(publication_text, 180) if publication_text else ""
    received_reference = _clean(trend_title, 160) if trend_title else ""
    subject = publication or product
    tone = ", ".join(_tone_label(item) for item in context.brand_tones[:3]) or "cercano"
    call_to_action = "Conoce la propuesta y escríbenos para recibir orientación."

    shot_count = 3 if duration_seconds <= 5 else 4
    durations = _duration_parts(duration_seconds, shot_count)
    shots_data = [
        (
            f"Presentación clara de {product} para captar atención.",
            "Plano vertical cercano y estable",
            _clean(f"{product} para ti", 120),
            _clean(f"{business_name} presenta {subject} para {audience}.", 240),
            "Corte limpio",
        ),
        (
            f"Detalle de la propuesta de {business_name} en un entorno de {category}.",
            "Movimiento vertical suave",
            _clean("Lo que puedes encontrar", 120),
            _clean(f"Una opción pensada para {audience}, con un tono {tone}.", 240),
            "Disolvencia breve",
        ),
        (
            f"Cierre visual con la identidad y el beneficio principal de {product}.",
            "Plano medio vertical con enfoque al producto",
            _clean("Da el siguiente paso", 120),
            _clean(call_to_action, 240),
            "Cierre suave",
        ),
    ]
    if shot_count == 4:
        shots_data.insert(
            2,
            (
                f"Aplicación o contexto de uso de {product}, sin afirmar resultados no recibidos.",
                "Paneo vertical lento",
                _clean("Una idea para considerar", 120),
                _clean(
                    f"Observa cómo encaja esta propuesta en una publicación para {audience}.",
                    240,
                ),
                "Corte por acción",
            ),
        )

    selected_shots_data = shots_data[: len(durations)]
    shots = [
        VideoShot(
            order=index,
            duration_seconds=shot_duration,
            visual=_clean(data[0], 240),
            camera=_clean(data[1], 120),
            on_screen_text=_clean(data[2], 120),
            voiceover=_clean(data[3], 240),
            transition=_clean(data[4], 60),
        )
        for index, (shot_duration, data) in enumerate(
            zip(durations, selected_shots_data, strict=True), start=1
        )
    ]
    if received_reference:
        reference_index = min(1, len(shots) - 1)
        shots[reference_index].voiceover = _clean(
            f"Referencia recibida para orientar el contenido: {received_reference}.", 240
        )

    storyboard_voiceover = " ".join(shot.voiceover for shot in shots)
    return VideoStoryboard(
        hook=_clean(f"{product}: {subject}", 160),
        duration_seconds=duration_seconds,
        aspect_ratio="9:16",
        voiceover=_clean(storyboard_voiceover, 600),
        music_direction=_clean(
            f"Ritmo {tone}, percusión ligera y ambiente limpio; usar audio autorizado.", 160
        ),
        shots=shots,
    )


def compose_prompt(
    storyboard: VideoStoryboard, context: BusinessGenerationContext
) -> tuple[str, str]:
    """Render the storyboard into a bounded provider prompt and exclusions."""

    business_name = _clean(context.name, 100) or "el negocio"
    product = _clean(context.primary_product, 100) or "la propuesta"
    tone = ", ".join(_tone_label(item) for item in context.brand_tones[:3]) or "cercano"
    shot_lines = " ".join(
        _clean(
            f"Toma {shot.order} ({shot.duration_seconds}s): visual={shot.visual}; "
            f"cámara={shot.camera}; texto={shot.on_screen_text}; voz={shot.voiceover}; "
            f"transición={shot.transition}.",
            520,
        )
        for shot in storyboard.shots
    )
    prompt = _clean(
        f"Genera un clip vertical editable de {storyboard.duration_seconds} segundos en "
        f"formato {storyboard.aspect_ratio}. Negocio: {business_name}. Propuesta: {product}. "
        f"Tono de marca: {tone}. Hook: {storyboard.hook}. "
        f"Dirección musical: {storyboard.music_direction}. {shot_lines}",
        4_000,
    )
    forbidden = ", ".join(_clean(item, 80) for item in context.forbidden_words[:8])
    negative_prompt = _clean(
        "Sin marcas de terceros, URLs, material con derechos no proporcionado, "
        "texto ilegible, rostros reconocibles no autorizados, cambios de formato ni "
        f"afirmaciones no sustentadas{f'; evitar también: {forbidden}' if forbidden else ''}.",
        600,
    )
    return prompt, negative_prompt
