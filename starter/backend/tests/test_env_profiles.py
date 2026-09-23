from __future__ import annotations

import pytest

from app.core.config import Settings

SECRET = "env-test-secret-do-not-echo"


def _minimal_production() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://app:password@db.example.com/hitrendy",
        "DATABASE_SSL_MODE": "require",
        "REDIS_URL": "redis://redis:6379/0",
        "REDIS_PROVIDER": "redis",
        "STORAGE_PROVIDER": "s3",
        "OBJECT_STORAGE_ENDPOINT": "https://s3.example.com",
        "OBJECT_STORAGE_ACCESS_KEY": "ak",
        "OBJECT_STORAGE_SECRET_KEY": "sk",
        "OBJECT_STORAGE_BUCKET": "bucket",
        "AI_PROVIDER": "openai-compatible",
        "AI_BASE_URL": "https://openrouter.ai/api/v1",
        "AI_API_KEY": SECRET,
        "AI_MODEL": "approved-model",
        "JWT_SECRET": "j" * 32,
        "ALLOWED_ORIGINS": "https://app.example.com",
        "ALLOWED_HOSTS": "api.example.com",
        "FRONTEND_URL": "https://app.example.com",
    }


def test_development_valid() -> None:
    settings = Settings({"APP_ENV": "development"})
    settings.validate_runtime_configuration()
    assert settings.app_env == "development"


def test_test_valid() -> None:
    settings = Settings({"APP_ENV": "test"})
    settings.validate_runtime_configuration()
    assert settings.app_env == "test"


def test_staging_valid() -> None:
    values = _minimal_production()
    values["APP_ENV"] = "staging"
    settings = Settings(values)
    settings.validate_runtime_configuration()
    assert settings.app_env == "staging"


def test_production_valid() -> None:
    settings = Settings(_minimal_production())
    settings.validate_runtime_configuration()
    assert settings.app_env == "production"


def test_production_rejects_http() -> None:
    values = _minimal_production()
    values["ALLOWED_ORIGINS"] = "http://app.example.com"
    with pytest.raises(RuntimeError, match="https"):
        Settings(values).validate_runtime_configuration()


def test_production_rejects_localhost_origin() -> None:
    values = _minimal_production()
    values["ALLOWED_ORIGINS"] = "https://app.example.com,http://localhost:3000"
    with pytest.raises(RuntimeError):
        Settings(values).validate_runtime_configuration()


def test_production_rejects_missing_allowed_hosts() -> None:
    values = _minimal_production()
    values.pop("ALLOWED_HOSTS")
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        Settings(values).validate_runtime_configuration()


def test_production_rejects_localhost_allowed_host() -> None:
    values = _minimal_production()
    values["ALLOWED_HOSTS"] = "localhost"
    with pytest.raises(RuntimeError, match="localhost"):
        Settings(values).validate_runtime_configuration()


def test_production_requires_https_frontend() -> None:
    values = _minimal_production()
    values["FRONTEND_URL"] = "http://app.example.com"
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        Settings(values).validate_runtime_configuration()


def test_production_rejects_cors_wildcard_with_credentials() -> None:
    values = _minimal_production()
    values["ALLOWED_ORIGINS"] = "*"
    with pytest.raises(RuntimeError, match="https"):
        Settings(values).validate_runtime_configuration()


def test_origins_are_normalized_and_deduplicated() -> None:
    settings = Settings({"APP_ENV": "development", "ALLOWED_ORIGINS": " http://localhost:3000/ ,http://localhost:3000"})
    assert settings.allowed_origin_list == ["http://localhost:3000"]


@pytest.mark.parametrize("origin", ["https://app.example.com/path", "https://app.example.com?x=1", "https://user:pass@app.example.com"])
def test_origins_reject_non_origin_values(origin: str) -> None:
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        Settings({"APP_ENV": "development", "ALLOWED_ORIGINS": origin})


def test_staging_requires_csrf_and_hosts() -> None:
    values = _minimal_production()
    values["APP_ENV"] = "staging"
    values["CSRF_ENABLED"] = "false"
    with pytest.raises(RuntimeError, match="CSRF_ENABLED"):
        Settings(values).validate_runtime_configuration()
    values["CSRF_ENABLED"] = "true"
    values.pop("ALLOWED_HOSTS")
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        Settings(values).validate_runtime_configuration()


def test_forwarded_allow_ips_rejects_invalid_and_production_wildcard() -> None:
    with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
        Settings({"APP_ENV": "development", "FORWARDED_ALLOW_IPS": "not-an-ip"}).validate_runtime_configuration()
    values = _minimal_production()
    values["FORWARDED_ALLOW_IPS"] = "*"
    with pytest.raises(RuntimeError, match="FORWARDED_ALLOW_IPS"):
        Settings(values).validate_runtime_configuration()


def test_invalid_env_rejected() -> None:
    with pytest.raises(RuntimeError, match="APP_ENV"):
        Settings({"APP_ENV": "invalid"}).validate_runtime_configuration()


def test_frontend_url_invalid() -> None:
    values = _minimal_production()
    values["FRONTEND_URL"] = "not-a-url"
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        Settings(values).validate_runtime_configuration()


def test_backend_url_embedded_credentials_rejected() -> None:
    values = _minimal_production()
    values["FRONTEND_URL"] = "https://user:pass@app.example.com"
    values["GOOGLE_SIGN_IN_ENABLED"] = "true"
    values["GOOGLE_CLIENT_ID"] = "test-id"
    values["GOOGLE_CLIENT_SECRET"] = "test-secret"
    values["GOOGLE_REDIRECT_URI"] = "https://app.example.com/auth/google/callback"
    with pytest.raises(RuntimeError):
        Settings(values).validate_runtime_configuration()


def test_samesite_none_without_secure_rejected() -> None:
    from app.core.cookies import _cookie_samesite, _cookie_secure

    assert _cookie_samesite() != "none" or _cookie_secure()


def test_missing_critical_config_fails_on_startup() -> None:
    values = _minimal_production()
    values["ALLOWED_ORIGINS"] = ""
    with pytest.raises(RuntimeError, match="ALLOWED_ORIGINS"):
        Settings(values).validate_runtime_configuration()
    values = _minimal_production()
    values["SESSION_COOKIE_NAME"] = ""
    with pytest.raises(RuntimeError, match="SESSION_COOKIE_NAME"):
        Settings(values).validate_runtime_configuration()
