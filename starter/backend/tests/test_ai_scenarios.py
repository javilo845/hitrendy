from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.domain.models import (
    BusinessGenerationContext,
    GeneratedShortVideoScript,
    GeneratedSocialPost,
)
from app.generation.contracts import ShortVideoScriptModelRequest, SocialPostModelRequest
from app.generation.evaluation import SocialPostEvaluator
from app.providers.content import DemoContentModelProvider

SCENARIO_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "fixtures"
    / "ai-regression-scenarios.v1.json"
)
EXPECTED_CATEGORIES = {"gastronomy", "fashion", "health", "art", "services", "retail"}
EXPECTED_PROMPT_SHAPES = {"direct", "vague", "contradictory"}


def _load_scenarios() -> tuple[str, list[dict[str, Any]]]:
    fixture = json.loads(SCENARIO_FIXTURE.read_text(encoding="utf-8"))
    return fixture["scenario_set_version"], fixture["scenarios"]


SCENARIO_SET_VERSION, SCENARIOS = _load_scenarios()


def _context(scenario: dict[str, Any]) -> BusinessGenerationContext:
    return BusinessGenerationContext(
        business_id=f"business_{scenario['id']}",
        name=scenario["business_name"],
        category=scenario["category"],
        city="Tegucigalpa",
        country="Honduras",
        primary_product=scenario["product"],
        target_audience=scenario["audience"],
        preferred_platforms=[scenario["platform"]],
        primary_objective=scenario["objective"],
        brand_tones=[scenario["tone"]],
        value_proposition="Una propuesta clara y responsable para su comunidad.",
        forbidden_words=["barato"],
    )


def test_regression_fixture_has_the_required_mvp_coverage() -> None:
    assert SCENARIO_SET_VERSION == "mvp-demo-v1"
    assert len(SCENARIOS) >= 30
    assert {scenario["category"] for scenario in SCENARIOS} == EXPECTED_CATEGORIES
    assert {scenario["prompt_shape"] for scenario in SCENARIOS} == EXPECTED_PROMPT_SHAPES
    assert len({scenario["id"] for scenario in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario["id"])
async def test_demo_provider_meets_the_versioned_regression_scenarios(
    scenario: dict[str, Any],
) -> None:
    context = _context(scenario)
    provider = DemoContentModelProvider()

    if scenario["artifact_type"] == "social_post":
        request = SocialPostModelRequest(
            prompt_version="social-copy@1.0.0",
            business=context,
            user_request=scenario["request"],
            platform=scenario["platform"],
            objective=scenario["objective"],
            tone=scenario["tone"],
            product_or_service=scenario["product"],
        )
        artifact = GeneratedSocialPost.model_validate(
            await provider.generate_social_post(request=request)
        )
        evaluation = SocialPostEvaluator().evaluate(artifact, request)

        assert evaluation.accepted, evaluation.issues
        rendered = " ".join(
            [artifact.hook, artifact.caption, artifact.call_to_action, artifact.visual_direction]
        ).casefold()
    else:
        request = ShortVideoScriptModelRequest(
            prompt_version="short-video-script@1.0.0",
            business=context,
            user_request=scenario["request"],
            platform=scenario["platform"],
            objective=scenario["objective"],
            tone=scenario["tone"],
            product_or_service=scenario["product"],
        )
        artifact = GeneratedShortVideoScript.model_validate(
            await provider.generate_short_video_script(request=request)
        )
        rendered = " ".join(
            [
                artifact.hook,
                artifact.caption,
                artifact.call_to_action,
                *(scene.visual for scene in artifact.scenes),
            ]
        ).casefold()
        assert artifact.scenes

    assert artifact.platform == scenario["platform"]
    assert scenario["product"].casefold() in rendered
    assert artifact.call_to_action.strip()
