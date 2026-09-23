from __future__ import annotations

from pydantic import ValidationError

from app.core.errors import AppError
from app.domain.models import AdvisorResponse
from app.generation.contracts import AdvisorModelRequest
from app.generation.evaluation import AdvisorEvaluator
from app.providers.content import ContentModelProvider
from app.services.generate_social_post import BusinessContextRepository


def _normalize_advisor_raw(raw: dict) -> dict:
    normalized = dict(raw) if isinstance(raw, dict) else {}
    
    # Summary
    if not normalized.get("summary") or not isinstance(normalized.get("summary"), str):
        normalized["summary"] = "Plan de asesoría estratégica para tu negocio y contenido."
    else:
        normalized["summary"] = str(normalized["summary"])[:1200]
        
    # Recommendations
    recs = normalized.get("recommendations", [])
    if isinstance(recs, str):
        recs = [recs]
    normalized_recs = []
    if isinstance(recs, list):
        for idx, item in enumerate(recs[:8]):
            if isinstance(item, str):
                parts = item.split(":", 1)
                if len(parts) == 2:
                    title = parts[0].strip()[:180] or f"Recomendación {idx + 1}"
                    desc = parts[1].strip()[:700] or item[:700]
                else:
                    title = item[:50] + ("..." if len(item) > 50 else "")
                    desc = item[:700]
                normalized_recs.append({"title": title, "description": desc, "priority": "high"})
            elif isinstance(item, dict):
                title = str(item.get("title") or f"Recomendación {idx + 1}")[:180]
                desc = str(item.get("description") or title)[:700]
                priority = item.get("priority") if item.get("priority") in ("high", "medium", "low") else "high"
                normalized_recs.append({"title": title, "description": desc, "priority": priority})
    if not normalized_recs:
        normalized_recs.append({
            "title": "Optimización de contenido",
            "description": "Publicar contenido constante enfocado en los productos clave de tu negocio.",
            "priority": "high"
        })
    normalized["recommendations"] = normalized_recs
    
    # Next actions
    actions = normalized.get("next_actions", [])
    if isinstance(actions, str):
        actions = [actions]
    normalized_actions = []
    if isinstance(actions, list):
        for item in actions[:8]:
            if isinstance(item, str) and item.strip():
                normalized_actions.append(item.strip()[:240])
            elif isinstance(item, dict):
                val = item.get("action") or item.get("title") or str(item)
                normalized_actions.append(str(val)[:240])
    if not normalized_actions:
        normalized_actions = [
            "Crear la primera publicación en el Studio.",
            "Revisar el diseño con una plantilla de Canva."
        ]
    normalized["next_actions"] = normalized_actions
    
    return normalized


class GenerateAdviceService:
    def __init__(
        self,
        business_repository: BusinessContextRepository,
        provider: ContentModelProvider,
        evaluator: AdvisorEvaluator | None = None,
    ) -> None:
        self._business_repository = business_repository
        self._provider = provider
        self.usage_metadata: dict[str, object] | None = None
        self._evaluator = evaluator or AdvisorEvaluator()

    async def execute(
        self, *, workspace_id: str, business_id: str, text: str, locale: str = "es"
    ) -> AdvisorResponse:
        context = await self._business_repository.get_for_generation(
            workspace_id=workspace_id, business_id=business_id
        )
        request = AdvisorModelRequest.from_context(
            context=context, user_request=text, locale=locale
        )
        raw = await self._provider.generate_advice(request=request)
        self.usage_metadata = raw.pop("__provider_metadata", None)
        normalized_raw = _normalize_advisor_raw(raw)
        try:
            response = AdvisorResponse.model_validate(normalized_raw)
        except ValidationError as exc:
            raise AppError(
                "GENERATION_CONTRACT_INVALID",
                "No pudimos preparar recomendaciones válidas. Inténtalo nuevamente.",
                status_code=502,
                retryable=True,
            ) from exc
        evaluation = self._evaluator.evaluate(response, context.forbidden_words)
        if not evaluation.accepted:
            raise AppError(
                "GENERATION_CONTRACT_INVALID",
                "No pudimos preparar recomendaciones válidas. Inténtalo nuevamente.",
                status_code=502,
                retryable=True,
            )
        return response
