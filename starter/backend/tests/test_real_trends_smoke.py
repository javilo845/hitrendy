"""Opt-in smoke: it is intentionally excluded from normal local and CI suites."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.trends.factory import configured_trend_sources

pytestmark = pytest.mark.skipif(
    not settings.run_real_trends_smoke or not settings.configured_real_trend_sources,
    reason="Smoke de tendencias omitido: requiere RUN_REAL_TRENDS_SMOKE=1 y una fuente configurada.",
)


@pytest.mark.asyncio
@pytest.mark.real_trends
async def test_configured_real_trend_sources_make_at_most_one_query_each() -> None:
    from tests.conftest import _TestingSessionFactory

    async with _TestingSessionFactory() as db:
        sources = configured_trend_sources(db)
        assert sources
        results = [await source.fetch(region="GLOBAL", category=None) for source in sources]
    assert all(result.status in {"success", "empty", "timeout", "error", "rate_limited", "quota_exhausted", "invalid"} for result in results)
