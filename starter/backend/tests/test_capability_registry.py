from __future__ import annotations

import pytest

from app.core.capabilities import (
    Capability,
    CapabilityOutcome,
    CapabilityRegistry,
    CapabilityRoute,
    CapabilityStatus,
    MemoryCapabilityOutcomeStore,
    NullCapabilityOutcomeStore,
    PublicCapabilityResponse,
    QualityLevel,
    Tier,
)
from app.core.config import settings


@pytest.fixture
def store() -> MemoryCapabilityOutcomeStore:
    return MemoryCapabilityOutcomeStore()


@pytest.fixture
def reg(store: MemoryCapabilityOutcomeStore) -> CapabilityRegistry:
    return CapabilityRegistry(outcome_store=store)


@pytest.fixture
def noop_reg() -> CapabilityRegistry:
    return CapabilityRegistry(outcome_store=NullCapabilityOutcomeStore())


@pytest.mark.asyncio
class TestTypes:
    async def test_all_capabilities_defined(self) -> None:
        names = {c.value for c in Capability.all()}
        expected = {"advisor", "copywriter", "vision_review", "image_generation", "video_generation", "trend_analysis"}
        assert names == expected

    async def test_all_quality_levels(self) -> None:
        assert QualityLevel.all() == [QualityLevel.FAST, QualityLevel.BALANCED, QualityLevel.QUALITY]

    async def test_all_statuses(self) -> None:
        statuses = {s.value for s in CapabilityStatus}
        expected = {"available", "unconfigured", "disabled", "restricted", "quota_exhausted", "payment_required", "degraded", "error"}
        assert statuses == expected

    async def test_public_capability_response_fields(self) -> None:
        fields = {"status", "tier", "quality_levels", "message", "next_reset_at", "fallback"}
        model_fields = set(PublicCapabilityResponse.model_fields.keys())
        assert fields == model_fields, f"PublicCapabilityResponse fields mismatch: {model_fields}"

    async def test_public_response_does_not_include_provider_key(self) -> None:
        fields = set(PublicCapabilityResponse.model_fields.keys())
        assert "provider_key" not in fields
        assert "provider" not in fields


@pytest.mark.asyncio
class TestConfigDerivationDemo:
    async def test_advisor_available_with_demo(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        advisor = snapshot["advisor"]
        assert advisor["status"] == "available"
        assert advisor["tier"] == "free"
        assert advisor["quality_levels"] == ["fast"]

    async def test_copywriter_available_with_demo(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        cw = snapshot["copywriter"]
        assert cw["status"] == "available"
        assert cw["tier"] == "free"
        assert cw["quality_levels"] == ["fast"]

    async def test_vision_review_available_with_demo(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        vr = snapshot["vision_review"]
        assert vr["status"] == "available"
        assert vr["tier"] == "free"
        assert vr["quality_levels"] == ["fast"]

    async def test_image_generation_disabled_by_default(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        ig = snapshot["image_generation"]
        assert ig["status"] == "disabled"
        assert ig["tier"] == "paid"
        assert ig["quality_levels"] == []

    async def test_video_generation_disabled_by_default(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        vg = snapshot["video_generation"]
        assert vg["status"] == "disabled"
        assert vg["tier"] == "paid"
        assert vg["quality_levels"] == []

    async def test_enabled_demo_video_is_available_free_with_storyboard_fallback(
        self, reg: CapabilityRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "app_env", "test")
        monkeypatch.setattr(settings, "video_provider", "demo")
        monkeypatch.setattr(settings, "video_generation_enabled", True)

        snapshot = await reg.get_public_snapshot()
        vg = snapshot["video_generation"]
        assert vg["status"] == "available"
        assert vg["tier"] == "free"
        assert vg["fallback"] == "storyboard"

    async def test_trend_analysis_disabled_by_default(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        ta = snapshot["trend_analysis"]
        assert ta["status"] == "disabled"
        assert ta["tier"] == "free"
        assert ta["quality_levels"] == []

    async def test_snapshot_contains_six_capabilities(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        assert len(snapshot) == 6
        for cap in Capability.all():
            assert cap.value in snapshot


@pytest.mark.asyncio
class TestProviderResolution:
    async def test_vision_uses_vision_provider(self, reg: CapabilityRegistry) -> None:
        """resolve vision_review must use the vision provider, not AI provider."""
        route = await reg.resolve(Capability.VISION_REVIEW, QualityLevel.FAST)
        assert route.provider_key == settings.vision_provider

    async def test_advisor_uses_ai_provider(self, reg: CapabilityRegistry) -> None:
        route = await reg.resolve(Capability.ADVISOR, QualityLevel.FAST)
        assert route.provider_key == settings.ai_provider

    async def test_copywriter_uses_ai_provider(self, reg: CapabilityRegistry) -> None:
        route = await reg.resolve(Capability.COPYWRITER, QualityLevel.FAST)
        assert route.provider_key == settings.ai_provider

    async def test_demo_vision_in_production_is_disabled(self, reg: CapabilityRegistry) -> None:
        original_env = settings.app_env
        settings.app_env = "production"
        try:
            info = reg.get_capability(Capability.VISION_REVIEW)
            assert info.status == CapabilityStatus.DISABLED
        finally:
            settings.app_env = original_env

    async def test_demo_text_in_production_is_disabled(self, reg: CapabilityRegistry) -> None:
        original_env = settings.app_env
        settings.app_env = "production"
        try:
            info = reg.get_capability(Capability.ADVISOR)
            assert info.status == CapabilityStatus.DISABLED
        finally:
            settings.app_env = original_env


@pytest.mark.asyncio
class TestTier:
    async def test_openai_compatible_uses_unknown_tier(self, reg: CapabilityRegistry) -> None:
        original_provider = settings.ai_provider
        settings.ai_provider = "openai-compatible"
        try:
            info = reg.get_capability(Capability.ADVISOR)
            assert info.tier == Tier.UNKNOWN
        finally:
            settings.ai_provider = original_provider

    async def test_demo_uses_free_tier(self, reg: CapabilityRegistry) -> None:
        info = reg.get_capability(Capability.ADVISOR)
        assert info.tier == Tier.FREE

    async def test_openrouter_only_advertises_configured_quality_levels(
        self, reg: CapabilityRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ai_provider", "openrouter")
        monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
        monkeypatch.setattr(settings, "openrouter_fast_model", "openrouter/free")
        monkeypatch.setattr(settings, "openrouter_balanced_model", "")
        monkeypatch.setattr(settings, "openrouter_quality_model", "")

        snapshot = await reg.get_public_snapshot()

        assert snapshot["advisor"]["status"] == "available"
        assert snapshot["advisor"]["tier"] == "free"
        assert snapshot["advisor"]["quality_levels"] == ["fast"]

    async def test_openrouter_advertises_explicit_paid_routes_only(
        self, reg: CapabilityRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ai_provider", "openrouter")
        monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
        monkeypatch.setattr(settings, "openrouter_fast_model", "openrouter/free")
        monkeypatch.setattr(settings, "openrouter_balanced_model", "approved-balanced")
        monkeypatch.setattr(settings, "openrouter_quality_model", "approved-quality")

        snapshot = await reg.get_public_snapshot()

        assert snapshot["copywriter"]["tier"] == "mixed"
        assert snapshot["copywriter"]["quality_levels"] == ["fast", "balanced", "quality"]

    async def test_openrouter_quality_levels_apply_only_to_text_capabilities(
        self, reg: CapabilityRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ai_provider", "openrouter")
        monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
        monkeypatch.setattr(settings, "openrouter_fast_model", "openrouter/free")
        monkeypatch.setattr(settings, "openrouter_balanced_model", "approved-balanced")
        monkeypatch.setattr(settings, "openrouter_quality_model", "approved-quality")
        monkeypatch.setattr(settings, "vision_provider", "demo")

        snapshot = await reg.get_public_snapshot()

        assert snapshot["advisor"]["quality_levels"] == ["fast", "balanced", "quality"]
        assert snapshot["copywriter"]["quality_levels"] == ["fast", "balanced", "quality"]
        assert snapshot["vision_review"]["quality_levels"] == ["fast"]

    async def test_unknown_ai_provider_is_unconfigured_unknown(self, reg: CapabilityRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "ai_provider", "unrecognized-provider")
        status, tier = reg._provider_status()
        assert status == CapabilityStatus.UNCONFIGURED
        assert tier == Tier.UNKNOWN

    async def test_unknown_vision_provider_is_unconfigured_unknown(
        self, reg: CapabilityRegistry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "vision_provider", "unrecognized-provider")
        status, tier = reg._vision_status()
        assert status == CapabilityStatus.UNCONFIGURED
        assert tier == Tier.UNKNOWN


@pytest.mark.asyncio
class TestSanitization:
    @pytest.mark.parametrize("sensitive_key", [
        "api_key", "secret", "token", "password", "database_url",
        "redis_url", "model_slug", "model_id", "balance",
    ])
    async def test_snapshot_no_sensitive_keys(self, reg: CapabilityRegistry, sensitive_key: str) -> None:
        snapshot = await reg.get_public_snapshot()
        snapshot_str = str(snapshot).lower()
        assert sensitive_key not in snapshot_str, f"Snapshot contiene '{sensitive_key}'"

    async def test_snapshot_no_credentials_in_values(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        snapshot_str = str(snapshot).lower()
        for pattern in ("sk-", "eyj", "-----begin", "akia"):
            assert pattern not in snapshot_str, f"Snapshot contiene '{pattern}'"

    async def test_snapshot_no_raw_error(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        snapshot_str = str(snapshot).lower()
        assert "raw_error" not in snapshot_str
        assert "traceback" not in snapshot_str

    async def test_snapshot_no_technical_model_names(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        snapshot_str = str(snapshot)
        assert "demo-v1" not in snapshot_str
        assert "gpt" not in snapshot_str

    async def test_response_model_does_not_contain_provider_key(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        snapshot_str = str(snapshot)
        assert "provider_key" not in snapshot_str


@pytest.mark.asyncio
class TestResolve:
    async def test_resolve_available_route(self, reg: CapabilityRegistry) -> None:
        route = await reg.resolve(Capability.ADVISOR, QualityLevel.FAST)
        assert route.capability == Capability.ADVISOR
        assert route.quality_level == QualityLevel.FAST

    async def test_resolve_unknown_capability(self, reg: CapabilityRegistry) -> None:
        with pytest.raises(Exception) as exc:
            await reg.resolve("nonexistent", QualityLevel.FAST)  # type: ignore[arg-type]
        assert "CAPABILITY" in str(exc.value)

    async def test_resolve_unknown_quality_level(self, reg: CapabilityRegistry) -> None:
        with pytest.raises(Exception) as exc:
            await reg.resolve(Capability.ADVISOR, "ultra")  # type: ignore[arg-type]
        assert "CAPABILITY_UNAVAILABLE" in str(exc.value)

    async def test_resolve_disabled_capability(self, reg: CapabilityRegistry) -> None:
        with pytest.raises(Exception) as exc:
            await reg.resolve(Capability.IMAGE_GENERATION, QualityLevel.FAST)
        assert "CAPABILITY" in str(exc.value)

    async def test_resolve_quality_level_not_permitted(self, reg: CapabilityRegistry) -> None:
        with pytest.raises(Exception) as exc:
            await reg.resolve(Capability.ADVISOR, QualityLevel.BALANCED)
        assert "CAPABILITY_UNAVAILABLE" in str(exc.value)

    async def test_resolve_image_generation_is_not_a_quality_route(
        self, reg: CapabilityRegistry
    ) -> None:
        """WAVE-011: image generation is chosen by format, never by quality.

        Before WAVE-011 the capability could only answer ``payment_required``.
        Now it becomes available once a provider and a model are configured,
        but it publishes no quality levels, so ``resolve`` is deliberately not
        its entry point: the images service reads the capability directly.
        """

        original = settings.image_generation_enabled
        settings.image_generation_enabled = True
        try:
            info = reg.get_base_capability(Capability.IMAGE_GENERATION)
            assert info.status == CapabilityStatus.AVAILABLE
            assert info.quality_levels == []
            with pytest.raises(Exception) as exc:
                await reg.resolve(Capability.IMAGE_GENERATION, QualityLevel.FAST)
            assert "CAPABILITY_UNAVAILABLE" in str(exc.value)
        finally:
            settings.image_generation_enabled = original

    async def test_resolve_image_generation_unconfigured_provider(
        self, reg: CapabilityRegistry
    ) -> None:
        original_enabled = settings.image_generation_enabled
        original_provider = settings.image_provider
        settings.image_generation_enabled = True
        settings.image_provider = "openrouter"
        try:
            info = reg.get_base_capability(Capability.IMAGE_GENERATION)
            assert info.status == CapabilityStatus.UNCONFIGURED
            assert info.tier == Tier.PAID
        finally:
            settings.image_generation_enabled = original_enabled
            settings.image_provider = original_provider


@pytest.mark.asyncio
class TestOutcomeStore:
    async def test_record_and_apply_success(self, reg: CapabilityRegistry, store: MemoryCapabilityOutcomeStore) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.SUCCESS)
        assert store.get(Capability.ADVISOR) == CapabilityOutcome.SUCCESS
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "available"

    async def test_timeout_causes_degraded(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.TIMEOUT)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "degraded"

    async def test_rate_limited_causes_degraded(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.RATE_LIMITED)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "degraded"

    async def test_quota_exhausted(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.QUOTA_EXHAUSTED)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "quota_exhausted"

    async def test_provider_error_causes_error_status(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.PROVIDER_ERROR)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "error"

    async def test_invalid_response_causes_degraded(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.INVALID_RESPONSE)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "degraded"

    async def test_success_recovers_from_degraded(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.TIMEOUT)
        assert reg.get_capability(Capability.ADVISOR).status == CapabilityStatus.DEGRADED
        await reg.record_outcome(route, CapabilityOutcome.SUCCESS)
        assert reg.get_capability(Capability.ADVISOR).status == CapabilityStatus.AVAILABLE

    async def test_payment_required_outcome(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg.record_outcome(route, CapabilityOutcome.PAYMENT_REQUIRED)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"]["status"] == "payment_required"
        assert snapshot["advisor"]["tier"] == "paid"

    async def test_outcome_does_not_affect_disabled(self, reg: CapabilityRegistry) -> None:
        route = CapabilityRoute(Capability.IMAGE_GENERATION, QualityLevel.FAST, "demo", Tier.PAID)
        await reg.record_outcome(route, CapabilityOutcome.PROVIDER_ERROR)
        snapshot = await reg.get_public_snapshot()
        assert snapshot["image_generation"]["status"] == "disabled"

    async def test_outcome_isolation_between_stores(self) -> None:
        store1 = MemoryCapabilityOutcomeStore()
        store2 = MemoryCapabilityOutcomeStore()
        reg1 = CapabilityRegistry(outcome_store=store1)
        reg2 = CapabilityRegistry(outcome_store=store2)
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        await reg1.record_outcome(route, CapabilityOutcome.PROVIDER_ERROR)
        s1 = await reg1.get_public_snapshot()
        s2 = await reg2.get_public_snapshot()
        assert s1["advisor"]["status"] == "error"
        assert s2["advisor"]["status"] == "available"

    async def test_outcome_does_not_grow_indefinitely(self, reg: CapabilityRegistry, store: MemoryCapabilityOutcomeStore) -> None:
        route = CapabilityRoute(Capability.ADVISOR, QualityLevel.FAST, "demo", Tier.FREE)
        for _ in range(100):
            await reg.record_outcome(route, CapabilityOutcome.TIMEOUT)
        assert len(store._data) == 1

    async def test_noop_store_never_affects_status(self, noop_reg: CapabilityRegistry) -> None:
        assert noop_reg.get_capability(Capability.ADVISOR).status == CapabilityStatus.AVAILABLE

    async def test_registry_with_noop_store_returns_snapshot(self, noop_reg: CapabilityRegistry) -> None:
        snapshot = await noop_reg.get_public_snapshot()
        assert len(snapshot) == 6


@pytest.mark.asyncio
class TestFallback:
    async def test_image_generation_fallback(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        assert snapshot["image_generation"]["fallback"] == "visual_brief"

    async def test_video_generation_fallback(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        assert snapshot["video_generation"]["fallback"] == "storyboard"

    async def test_trend_analysis_fallback(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        assert snapshot["trend_analysis"]["fallback"] == "business_recommendations"

    async def test_advisor_no_fallback(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"].get("fallback") is None


@pytest.mark.asyncio
class TestPublicMessages:
    async def test_available_no_message(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        assert snapshot["advisor"].get("message") is None

    async def test_disabled_image_message(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        msg = snapshot["image_generation"].get("message")
        assert msg and "imágenes" in msg.lower()

    async def test_disabled_video_message(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        msg = snapshot["video_generation"].get("message")
        assert msg and "video" in msg.lower()

    async def test_disabled_trends_message(self, reg: CapabilityRegistry) -> None:
        snapshot = await reg.get_public_snapshot()
        msg = snapshot["trend_analysis"].get("message")
        assert msg and "tendencia" in msg.lower()
