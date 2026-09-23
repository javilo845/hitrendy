from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import BusinessGenerationContext, GeneratedSocialPost
from app.generation.contracts import AdvisorModelRequest, SocialPostModelRequest
from app.generation.evaluation import AdvisorEvaluator, SocialPostEvaluator
from app.providers.content import ContentModelProvider


@dataclass(frozen=True)
class ModelEvaluationResult:
    candidate: str
    passed: int
    total: int
    failures: tuple[str, ...]


def evaluation_requests() -> list[tuple[AdvisorModelRequest, SocialPostModelRequest]]:
    """Small deterministic suite; live execution is opt-in and never runs in CI."""
    result: list[tuple[AdvisorModelRequest, SocialPostModelRequest]] = []
    locales = (("es", "artesanal"), ("en", "handcrafted"), ("pt", "artesanal"))
    for locale, preferred in locales:
        business = BusinessGenerationContext(
            business_id=f"eval-{locale}", name="Café Aurora", category="gastronomy",
            city="Tegucigalpa", country="Honduras", primary_product="café frío",
            target_audience="jóvenes profesionales", preferred_platforms=["instagram"],
            primary_objective="engagement", brand_tones=["friendly"],
            value_proposition="Bebidas preparadas al momento.", preferred_words=[preferred],
            forbidden_words=["barato"],
        )
        advisor = AdvisorModelRequest(business=business, user_request="Dame una recomendación accionable.", locale=locale)
        copywriter = SocialPostModelRequest(
            business=business, user_request="Crea un caption accionable.", locale=locale,
            platform="instagram", tone="friendly", objective="engagement",
            prompt_version="model-evaluation@1.0.0", product_or_service=business.primary_product,
        )
        result.append((advisor, copywriter))
    return result


async def evaluate_candidate(provider: ContentModelProvider) -> ModelEvaluationResult:
    failures: list[str] = []
    requests = evaluation_requests()
    for advisor_request, copy_request in requests:
        try:
            advice = await provider.generate_advice(request=advisor_request)
            from app.domain.models import AdvisorResponse

            validated_advice = AdvisorResponse.model_validate(advice)
            if not AdvisorEvaluator().evaluate(validated_advice, advisor_request.business.forbidden_words).accepted:
                failures.append(f"advisor:{advisor_request.locale}:brand")
            copy = await provider.generate_social_post(request=copy_request)
            validated_copy = GeneratedSocialPost.model_validate(copy)
            evaluation = SocialPostEvaluator().evaluate(validated_copy, copy_request)
            rendered = " ".join((validated_copy.hook, validated_copy.caption)).casefold()
            if not evaluation.accepted or copy_request.business.preferred_words[0].casefold() not in rendered:
                failures.append(f"copywriter:{copy_request.locale}:contract-or-brand")
        except Exception:
            failures.append(f"{advisor_request.locale}:invalid-response")
    return ModelEvaluationResult(
        candidate=provider.model_name, passed=len(requests) * 2 - len(failures),
        total=len(requests) * 2,
        failures=tuple(failures),
    )
