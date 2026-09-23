from __future__ import annotations

import pytest

from app.core.capabilities import QualityLevel
from app.core.config import Settings
from app.db.session import get_database_engine_options
from app.providers.content import DemoContentModelProvider, OpenAICompatibleContentModelProvider
from app.providers.factory import (
    get_content_provider,
    get_image_generation_provider,
    get_video_generation_provider,
    get_vision_provider,
)
from app.providers.images import OpenAIImageGenerationProvider
from app.providers.video import OpenAIVideoGenerationProvider
from app.providers.vision import DemoVisionReviewProvider

SECRET = "sentinel-config-secret-do-not-echo"


def _production_values() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://app:password@db/hitrendy",
        "REDIS_URL": "redis://redis:6379/0",
        "OBJECT_STORAGE_PROVIDER": "s3",
        "OBJECT_STORAGE_ENDPOINT": "https://storage.example",
        "OBJECT_STORAGE_ACCESS_KEY": "storage-access",
        "OBJECT_STORAGE_SECRET_KEY": "storage-secret",
        "OBJECT_STORAGE_BUCKET": "hitrendy-private",
        "AI_PROVIDER": "openai-compatible",
        "AI_BASE_URL": "https://openrouter.ai/api/v1",
        "AI_API_KEY": SECRET,
        "AI_MODEL": "approved-model",
        "AI_TIMEOUT_SECONDS": "30",
        "AI_MAX_RETRIES": "1",
        "AI_RETRY_BASE_SECONDS": "0.5",
        "VISION_PROVIDER": "demo",
        "VISION_MODEL": "demo-vision-v1",
        "JWT_SECRET": "j" * 32,
        "ALLOWED_ORIGINS": "https://app.example",
        "ALLOWED_HOSTS": "app.example,api.example",
        "FRONTEND_URL": "https://app.example",
    }


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_demo_provider_requires_no_ai_credentials_outside_production(app_env: str) -> None:
    settings = Settings(
        {
            "APP_ENV": app_env,
            "AI_PROVIDER": "demo",
            "AI_MODEL": "demo-v1",
            "AI_BASE_URL": "",
            "AI_API_KEY": "",
            "VISION_PROVIDER": "demo",
        }
    )

    settings.validate_runtime_configuration()

    assert settings.ai_provider == "demo"
    assert settings.ai_api_key == ""
    assert settings.ai_max_retries == 1
    assert settings.ai_retry_base_seconds == 0.5
    assert settings.run_real_ai_smoke is False


def test_openai_compatible_configuration_is_valid_and_typed() -> None:
    values = _production_values()
    settings = Settings(values)

    settings.validate_runtime_configuration()

    assert settings.ai_provider == "openai-compatible"
    assert settings.ai_base_url == "https://openrouter.ai/api/v1"
    assert settings.ai_max_retries == 1
    assert isinstance(settings.ai_timeout_seconds, float)
    assert isinstance(settings.run_real_ai_smoke, bool)


def test_openai_api_key_is_reused_by_text_and_vision_routes() -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "OPENAI_API_KEY": SECRET,
            "AI_PROVIDER": "openai-compatible",
            "AI_MODEL": "gpt-5.6",
            "VISION_PROVIDER": "openai-compatible",
            "VISION_MODEL": "gpt-5.6",
        }
    )

    configured.validate_runtime_configuration()

    assert configured.ai_api_key == SECRET
    assert configured.ai_base_url == "https://api.openai.com/v1"
    assert configured.vision_api_key == SECRET
    assert configured.vision_base_url == "https://api.openai.com/v1"


def test_openai_media_configuration_is_valid_with_one_key() -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "OPENAI_API_KEY": SECRET,
            "IMAGE_GENERATION_ENABLED": "1",
            "IMAGE_PROVIDER": "openai",
            "IMAGE_GENERATION_MODEL": "gpt-image-2",
            "IMAGE_GENERATION_ALLOWED_MODELS": "gpt-image-2",
            "VIDEO_GENERATION_ENABLED": "1",
            "VIDEO_PROVIDER": "openai",
            "VIDEO_GENERATION_MODEL": "sora-2",
            "VIDEO_GENERATION_ALLOWED_MODELS": "sora-2",
            "VIDEO_GENERATION_ALLOWED_DURATIONS": "16,20",
        }
    )

    configured.validate_runtime_configuration()

    assert configured.image_generation_configured is True
    assert configured.video_generation_configured is True


def test_production_allows_phase1_demo_vision() -> None:
    settings = Settings(_production_values())

    settings.validate_runtime_configuration()

    assert settings.vision_provider == "demo"


@pytest.mark.parametrize("field", ["AI_BASE_URL", "AI_API_KEY", "AI_MODEL"])
def test_openai_compatible_configuration_requires_all_real_fields(field: str) -> None:
    values = _production_values()
    values.pop(field)
    settings = Settings(values)

    with pytest.raises(RuntimeError, match=field):
        settings.validate_runtime_configuration()


@pytest.mark.parametrize("value", ["-1", "3", "not-a-number"])
def test_retry_count_is_bounded(value: str) -> None:
    values = {"AI_MAX_RETRIES": value}

    with pytest.raises(RuntimeError, match="AI_MAX_RETRIES"):
        Settings(values)


@pytest.mark.parametrize("value", ["0", "-0.1", "not-a-number"])
def test_retry_base_and_timeout_must_be_positive(value: str) -> None:
    with pytest.raises(RuntimeError):
        Settings({"AI_RETRY_BASE_SECONDS": value})
    with pytest.raises(RuntimeError):
        Settings({"AI_TIMEOUT_SECONDS": value})


def test_invalid_provider_values_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="AI_PROVIDER"):
        Settings({"AI_PROVIDER": "unknown"}).validate_runtime_configuration()
    with pytest.raises(RuntimeError, match="VISION_PROVIDER"):
        Settings({"VISION_PROVIDER": "unknown"}).validate_runtime_configuration()


@pytest.mark.parametrize("durations", ["7", "15,30"])
def test_demo_video_configuration_rejects_missing_fixtures(durations: str) -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "VIDEO_PROVIDER": "demo",
            "VIDEO_GENERATION_ALLOWED_DURATIONS": durations,
        }
    )

    with pytest.raises(RuntimeError, match="VIDEO_GENERATION_ALLOWED_DURATIONS"):
        configured.validate_runtime_configuration()


def test_demo_video_configuration_accepts_only_exact_fixture_durations() -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "VIDEO_PROVIDER": "demo",
            "VIDEO_GENERATION_ALLOWED_DURATIONS": "10,5",
        }
    )

    configured.validate_runtime_configuration()
    assert configured.video_generation_allowed_durations == (5, 10)


def test_configuration_errors_do_not_echo_secret() -> None:
    settings = Settings(
        {
            "AI_PROVIDER": "openai-compatible",
            "AI_API_KEY": SECRET,
            "AI_BASE_URL": "not-a-url",
            "AI_MODEL": "approved-model",
        }
    )

    with pytest.raises(RuntimeError) as caught:
        settings.validate_runtime_configuration()

    assert SECRET not in str(caught.value)


def test_factory_selects_explicit_demo_and_openai_compatible_providers(monkeypatch) -> None:
    demo_settings = Settings({"APP_ENV": "development", "AI_PROVIDER": "demo"})
    monkeypatch.setattr("app.providers.factory.settings", demo_settings)
    assert isinstance(get_content_provider(), DemoContentModelProvider)

    real_settings = Settings(
        {
            "APP_ENV": "development",
            "AI_PROVIDER": "openai-compatible",
            "AI_BASE_URL": "https://openrouter.ai/api/v1",
            "AI_API_KEY": SECRET,
            "AI_MODEL": "approved-model",
        }
    )
    monkeypatch.setattr("app.providers.factory.settings", real_settings)
    provider = get_content_provider()
    assert isinstance(provider, OpenAICompatibleContentModelProvider)
    assert provider.model_name == "approved-model"


def test_factory_selects_direct_openai_media_providers(monkeypatch) -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "OPENAI_API_KEY": SECRET,
            "IMAGE_GENERATION_ENABLED": "1",
            "IMAGE_PROVIDER": "openai",
            "IMAGE_GENERATION_MODEL": "gpt-image-2",
            "IMAGE_GENERATION_ALLOWED_MODELS": "gpt-image-2",
            "VIDEO_GENERATION_ENABLED": "1",
            "VIDEO_PROVIDER": "openai",
            "VIDEO_GENERATION_MODEL": "sora-2",
            "VIDEO_GENERATION_ALLOWED_MODELS": "sora-2",
            "VIDEO_GENERATION_ALLOWED_DURATIONS": "16,20",
        }
    )
    monkeypatch.setattr("app.providers.factory.settings", configured)

    assert isinstance(get_image_generation_provider(), OpenAIImageGenerationProvider)
    assert isinstance(get_video_generation_provider(), OpenAIVideoGenerationProvider)


def test_openrouter_configuration_uses_the_existing_openai_compatible_provider(monkeypatch) -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": SECRET,
            "OPENROUTER_FAST_MODEL": "openrouter/free",
        }
    )
    configured.validate_runtime_configuration()
    monkeypatch.setattr("app.providers.factory.settings", configured)

    provider = get_content_provider()

    assert isinstance(provider, OpenAICompatibleContentModelProvider)
    assert provider.provider_name == "openrouter"
    assert provider.model_name == "openrouter/free"
    assert provider._structured_output is True


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_production_like_openrouter_configuration_is_valid(app_env: str) -> None:
    values = _production_values()
    values.update(
        {
            "APP_ENV": app_env,
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": SECRET,
            "OPENROUTER_FAST_MODEL": "openrouter/free",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
        }
    )
    settings = Settings(values)

    settings.validate_runtime_configuration()

    assert settings.ai_provider == "openrouter"


def test_production_rejects_demo_text_provider() -> None:
    values = _production_values()
    values["AI_PROVIDER"] = "demo"

    with pytest.raises(RuntimeError, match="AI_PROVIDER"):
        Settings(values).validate_runtime_configuration()


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("OPENROUTER_API_KEY", "", "OPENROUTER_API_KEY"),
        ("OPENROUTER_BASE_URL", "http://openrouter.example/v1", "OPENROUTER_BASE_URL"),
    ],
)
def test_production_openrouter_requires_key_and_https(field: str, value: str, match: str) -> None:
    values = _production_values()
    values.update(
        {
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": SECRET,
            "OPENROUTER_FAST_MODEL": "openrouter/free",
            "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
            field: value,
        }
    )

    with pytest.raises(RuntimeError, match=match):
        Settings(values).validate_runtime_configuration()


def test_openrouter_routes_select_only_explicit_approved_models(monkeypatch) -> None:
    configured = Settings(
        {
            "APP_ENV": "development",
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": SECRET,
            "OPENROUTER_FAST_MODEL": "openrouter/free",
            "OPENROUTER_BALANCED_MODEL": "approved/balanced",
            "OPENROUTER_QUALITY_MODEL": "approved/quality",
        }
    )
    monkeypatch.setattr("app.providers.factory.settings", configured)

    assert get_content_provider(quality_level=QualityLevel.FAST).model_name == "openrouter/free"
    assert (
        get_content_provider(quality_level=QualityLevel.BALANCED).model_name == "approved/balanced"
    )
    assert get_content_provider(quality_level=QualityLevel.QUALITY).model_name == "approved/quality"


def test_openrouter_configuration_fails_closed_without_a_key() -> None:
    settings = Settings({"AI_PROVIDER": "openrouter"})

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        settings.validate_runtime_configuration()


@pytest.mark.parametrize("fast_model", ["paid/model", "arbitrary/model"])
def test_openrouter_fast_route_rejects_any_non_free_model(
    monkeypatch: pytest.MonkeyPatch, fast_model: str
) -> None:
    configured = Settings(
        {
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": SECRET,
            "OPENROUTER_FAST_MODEL": fast_model,
        }
    )
    with pytest.raises(RuntimeError, match="OPENROUTER_FAST_MODEL"):
        configured.validate_runtime_configuration()

    # Factory validation remains closed if a caller mutates Settings directly.
    monkeypatch.setattr("app.providers.factory.settings", configured)
    with pytest.raises(Exception, match="CAPABILITY_UNAVAILABLE"):
        get_content_provider()


def test_factory_keeps_demo_vision_available_in_production(monkeypatch) -> None:
    monkeypatch.setattr("app.providers.factory.settings", Settings(_production_values()))

    assert isinstance(get_vision_provider(), DemoVisionReviewProvider)


def test_postgres_remote_configuration_uses_ssl_and_bounded_pool() -> None:
    settings = Settings(
        {
            "DATABASE_URL": "postgresql://app:password@db.example.com:6543/postgres",
            "DATABASE_SSL_MODE": "require",
            "DATABASE_POOL_SIZE": "4",
            "DATABASE_MAX_OVERFLOW": "6",
            "DATABASE_POOL_TIMEOUT": "20",
            "DATABASE_POOL_RECYCLE": "900",
        }
    )

    settings.validate_runtime_configuration()

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_ssl_mode == "require"
    assert settings.database_pool_size == 4
    assert settings.database_max_overflow == 6


def test_postgres_engine_options_include_ssl_and_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    remote_settings = Settings(
        {
            "DATABASE_URL": "postgresql+psycopg://app:password@db.example.com/postgres",
            "DATABASE_SSL_MODE": "require",
            "DATABASE_POOL_SIZE": "4",
            "DATABASE_MAX_OVERFLOW": "6",
            "DATABASE_POOL_TIMEOUT": "20",
            "DATABASE_POOL_RECYCLE": "900",
        }
    )
    monkeypatch.setattr("app.db.session.settings", remote_settings)

    assert get_database_engine_options() == {
        "pool_size": 4,
        "max_overflow": 6,
        "pool_timeout": 20,
        "pool_recycle": 900,
        "pool_pre_ping": True,
        "connect_args": {"sslmode": "require"},
    }


def test_remote_postgres_in_production_requires_ssl() -> None:
    values = _production_values()
    values["DATABASE_URL"] = "postgresql+psycopg://app:password@db.example.com/postgres"
    values["DATABASE_SSL_MODE"] = "disable"

    with pytest.raises(RuntimeError, match="DATABASE_SSL_MODE"):
        Settings(values).validate_runtime_configuration()


@pytest.mark.parametrize(
    "values, message",
    [
        ({"STORAGE_PROVIDER": "supabase"}, "Supabase Storage"),
        ({"STORAGE_PROVIDER": "unknown"}, "OBJECT_STORAGE_PROVIDER"),
        ({"REDIS_PROVIDER": "redis"}, "REDIS_URL"),
        ({"REDIS_PROVIDER": "memory", "REDIS_REQUIRED": "1"}, "REDIS_REQUIRED"),
    ],
)
def test_cloud_configuration_fails_closed_when_incomplete(
    values: dict[str, str], message: str
) -> None:
    with pytest.raises(RuntimeError, match=message):
        Settings(values).validate_runtime_configuration()


def test_disabled_storage_and_memory_redis_are_valid_for_local_work() -> None:
    settings = Settings(
        {
            "APP_ENV": "development",
            "STORAGE_PROVIDER": "disabled",
            "REDIS_PROVIDER": "memory",
        }
    )

    settings.validate_runtime_configuration()

    assert settings.object_storage_provider == "disabled"
    assert settings.redis_provider == "memory"
