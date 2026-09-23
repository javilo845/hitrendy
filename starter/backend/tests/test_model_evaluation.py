from __future__ import annotations

import pytest

from app.generation.model_evaluation import evaluate_candidate, evaluation_requests
from app.providers.content import DemoContentModelProvider


def test_evaluation_fixture_covers_required_languages_and_brand_constraints() -> None:
    requests = evaluation_requests()
    assert {advisor.locale for advisor, _ in requests} == {"es", "en", "pt"}
    assert {copy.locale for _, copy in requests} == {"es", "en", "pt"}
    for advisor, copy in requests:
        assert advisor.business.value_proposition
        assert advisor.business.primary_product
        assert advisor.business.target_audience
        assert advisor.business.preferred_words
        assert advisor.business.forbidden_words
        assert copy.platform == "instagram"
        assert copy.objective == "engagement"


@pytest.mark.asyncio
async def test_demo_evaluation_is_deterministic_and_economical() -> None:
    result = await evaluate_candidate(DemoContentModelProvider())
    assert result.total == 6
    assert result.passed == result.total
    assert result.failures == ()
