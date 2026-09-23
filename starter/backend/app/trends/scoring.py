from __future__ import annotations

from datetime import UTC, datetime

SCORING_VERSION = "trend-v1"
RELEVANCE_VERSION = "workspace-relevance-v1"


def score(
    *,
    observed_at: datetime,
    evidence_count: int,
    source_count: int,
    now: datetime,
) -> tuple[dict[str, float], float]:
    age_hours = max(0.0, (now - observed_at.astimezone(UTC)).total_seconds() / 3600)
    freshness = max(0.0, round(1 - min(age_hours, 168) / 168, 6))
    components = {
        "freshness": freshness,
        "evidence": min(1.0, evidence_count / 3),
        "source_diversity": min(1.0, source_count / 2),
    }
    total = round(
        sum(
            components[key] * weight
            for key, weight in {
                "freshness": 0.35,
                "evidence": 0.35,
                "source_diversity": 0.30,
            }.items()
        ),
        6,
    )
    return components, total


def workspace_relevance(
    *, trend_category: str | None, region: str, business: object
) -> tuple[dict[str, float], float]:
    category = (
        1.0 if trend_category and trend_category == getattr(business, "category", None) else 0.0
    )
    local = (
        1.0
        if region.casefold()
        in {getattr(business, "country", "").casefold(), getattr(business, "city", "").casefold()}
        else 0.0
    )
    components = {"business_category": category, "regional_match": local}
    return components, round(category * 0.6 + local * 0.4, 6)
