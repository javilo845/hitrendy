from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import AdvisorResponse, GeneratedSocialPost
from app.generation.contracts import SocialPostModelRequest


@dataclass(frozen=True)
class GenerationEvaluation:
    accepted: bool
    issues: tuple[str, ...]


class SocialPostEvaluator:
    """Deterministic release checks; subjective rubric scoring remains a later provider-independent layer."""

    def evaluate(
        self, artifact: GeneratedSocialPost, request: SocialPostModelRequest
    ) -> GenerationEvaluation:
        issues: list[str] = []
        if artifact.platform != request.platform:
            issues.append("La plataforma no coincide con la solicitada.")
        if not artifact.call_to_action.strip():
            issues.append("Falta un llamado a la acción.")
        forbidden = request.business.forbidden_words
        rendered = " ".join([artifact.hook, artifact.caption, artifact.call_to_action]).casefold()
        if contains_forbidden_word(rendered, forbidden):
            issues.append("El contenido incluye un término prohibido por la marca.")
        if re.search(r"(?:\$|l\.?|hnl|usd)\s*\d|\d+\s*%", rendered, flags=re.IGNORECASE):
            user_prompt_case = request.user_request.casefold()
            if not re.search(r"(?:\$|l\.?|hnl|usd)\s*\d|\d+\s*%", user_prompt_case, flags=re.IGNORECASE):
                issues.append("El contenido incluye un precio o descuento no confirmado.")
        if re.search(
            r"\b(garantizado|garantizada|resultados garantizados|100% efectivo)\b",
            rendered,
            flags=re.IGNORECASE,
        ):
            issues.append("El contenido incluye una garantía no sustentada.")
        return GenerationEvaluation(accepted=not issues, issues=tuple(issues))


class AdvisorEvaluator:
    """Reject unsafe brand wording without mutating model text."""

    def evaluate(self, response: AdvisorResponse, forbidden_words: list[str]) -> GenerationEvaluation:
        rendered = " ".join(
            [
                response.summary,
                *response.next_actions,
                *(item.title for item in response.recommendations),
                *(item.description for item in response.recommendations),
            ]
        ).casefold()
        if contains_forbidden_word(rendered, forbidden_words):
            return GenerationEvaluation(False, ("El contenido incluye un término prohibido por la marca.",))
        return GenerationEvaluation(True, ())


def contains_forbidden_word(rendered: str, forbidden_words: list[str]) -> bool:
    """Match complete terms/phrases; never blindly replace substrings (e.g. bar/barista)."""
    for word in forbidden_words:
        candidate = word.strip().casefold()
        if candidate and re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", rendered):
            return True
    return False
