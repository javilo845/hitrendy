from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.admin.usage import execute_reset
from app.conversations.models import AIUsageEvent
from app.core.config import settings
from app.core.errors import AppError
from app.identity.models import AuthSession, PendingSignup
from app.identity.password_reset import token_hash
from app.operations.email import clear_demo_messages, demo_messages
from app.operations.invites import invite_code_hash
from app.operations.models import (
    AbuseReport,
    BetaInvite,
    PasswordResetToken,
    ProductFeedback,
    UsageAdjustment,
)
from app.operations.monitoring import MetricsRegistry
from app.services.usage_policy import ensure_generation_allowed, month_cost


@pytest.fixture(autouse=True)
def beta_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_provider", "demo")
    monkeypatch.setattr(settings, "beta_invites_enabled", False)
    monkeypatch.setattr(settings, "usage_enforcement_mode", "off")
    monkeypatch.setattr(settings, "monthly_ai_budget_usd", 0.0)
    clear_demo_messages()


def _demo_reset_token() -> str:
    link = demo_messages()[0].text.rsplit(": ", 1)[1].splitlines()[0]
    return parse_qs(urlparse(link).query)["token"][0]


@pytest.mark.asyncio
async def test_public_policies_and_metrics_are_available(client) -> None:
    policies = await client.get("/api/v1/policies")
    assert policies.status_code == 200
    assert {"privacy", "terms", "support", "email_verification", "closed_beta"} <= policies.json().keys()

    metrics = await client.get("/health/metrics")
    assert metrics.status_code == 200
    assert "hitrendy_http_requests_total" in metrics.text


@pytest.mark.asyncio
async def test_metrics_can_require_a_bearer_token(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "metrics_auth_token", "metrics-test-token")

    assert (await client.get("/health/metrics")).status_code == 404
    assert (
        await client.get("/health/metrics", headers={"Authorization": "Bearer wrong-token"})
    ).status_code == 404
    authorized = await client.get(
        "/health/metrics", headers={"Authorization": "Bearer metrics-test-token"}
    )
    assert authorized.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_is_generic_and_single_use(client, db_session) -> None:
    first = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "test@example.com"},
    )
    unknown = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "nobody@example.com"},
    )
    assert first.status_code == unknown.status_code == 202
    assert first.json() == unknown.json()
    assert len(demo_messages()) == 1

    token = _demo_reset_token()
    row = await db_session.scalar(select(PasswordResetToken))
    assert row is not None and row.token_hash == token_hash(token)

    confirmed = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "una-nueva-clave-123"},
    )
    assert confirmed.status_code == 200
    assert await db_session.scalar(select(AuthSession).where(AuthSession.user_id == "usr_test_001")) is None

    reused = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "otra-clave-segura-123"},
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "PASSWORD_RESET_INVALID"

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "una-nueva-clave-123"},
    )
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_password_reset_expiry_is_rejected(client, db_session) -> None:
    await client.post("/api/v1/auth/password-reset/request", json={"email": "test@example.com"})
    token = _demo_reset_token()
    row = await db_session.scalar(select(PasswordResetToken))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "una-nueva-clave-123"},
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "PASSWORD_RESET_EXPIRED"


@pytest.mark.asyncio
async def test_feedback_and_abuse_are_authenticated_and_idempotent(client, db_session) -> None:
    feedback = await client.post(
        "/api/v1/feedback",
        headers={"Idempotency-Key": "feedback-1"},
        json={"category": "idea", "rating": 5, "message": "Me gustaría exportar el borrador."},
    )
    repeated = await client.post(
        "/api/v1/feedback",
        headers={"Idempotency-Key": "feedback-1"},
        json={"category": "idea", "rating": 5, "message": "Me gustaría exportar el borrador."},
    )
    assert feedback.status_code == repeated.status_code == 201
    assert feedback.json()["id"] == repeated.json()["id"]
    assert await db_session.scalar(select(ProductFeedback)) is not None

    abuse = await client.post(
        "/api/v1/abuse/reports",
        json={"category": "spam", "message": "Este contenido parece automatizado.", "resource_id": "artifact-1"},
    )
    assert abuse.status_code == 201
    assert await db_session.scalar(select(AbuseReport)) is not None


@pytest.mark.asyncio
async def test_feedback_and_abuse_reject_anonymous_requests(client) -> None:
    client.cookies.delete(settings.session_cookie_name)
    feedback = await client.post(
        "/api/v1/feedback",
        json={"category": "support", "message": "No debería entrar."},
    )
    abuse = await client.post(
        "/api/v1/abuse/reports",
        json={"category": "other", "message": "No debería entrar."},
    )
    assert feedback.status_code == abuse.status_code == 401


@pytest.mark.asyncio
async def test_closed_beta_invite_is_bound_to_email_and_redeemed(client, db_session, monkeypatch) -> None:
    monkeypatch.setattr(settings, "beta_invites_enabled", True)
    code = "htb_test_invite_123456789"
    db_session.add(
        BetaInvite(
            code_hash=invite_code_hash(code),
            email_normalized="new@example.com",
            created_by="ops@example.com",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    client.cookies.delete(settings.session_cookie_name)

    started = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": "new@example.com",
            "name": "Nueva persona",
            "password": "una-clave-nueva-123",
            "interface_locale": "es",
            "invite_code": code,
        },
    )
    assert started.status_code == 201
    pending = await db_session.scalar(select(PendingSignup).where(PendingSignup.email_normalized == "new@example.com"))
    assert pending is not None and pending.beta_invite_id is not None

    wrong_email = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": "wrong@example.com",
            "name": "Otra",
            "password": "una-clave-nueva-123",
            "interface_locale": "es",
            "invite_code": code,
        },
    )
    assert wrong_email.status_code == 403
    assert wrong_email.json()["error"]["code"] == "BETA_INVITE_INVALID"

    missing = await client.post(
        "/api/v1/auth/signup/start",
        json={"email": "other@example.com", "name": "Otra", "password": "una-clave-nueva-123"},
    )
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "BETA_INVITE_REQUIRED"


@pytest.mark.asyncio
async def test_cost_cap_blocks_only_in_hard_mode(client, db_session, monkeypatch) -> None:
    db_session.add(
        AIUsageEvent(
            workspace_id="ws_test_001",
            user_id="usr_test_001",
            capability="copywriter",
            quality_level="fast",
            provider="openrouter",
            requested_model="hidden-model",
            reported_cost=Decimal("1.00"),
            currency="USD",
            outcome="success",
        )
    )
    await db_session.commit()
    monkeypatch.setattr(settings, "usage_enforcement_mode", "hard")
    monkeypatch.setattr(settings, "monthly_ai_budget_usd", 1.0)

    with pytest.raises(AppError) as blocked:
        await ensure_generation_allowed(db_session, workspace_id="ws_test_001")
    assert blocked.value.code == "COST_CAP_REACHED"


@pytest.mark.asyncio
async def test_usage_reset_is_audited_and_keeps_ledger_immutable(client, db_session, monkeypatch) -> None:
    db_session.add(
        AIUsageEvent(
            workspace_id="ws_test_001",
            user_id="usr_test_001",
            capability="copywriter",
            quality_level="fast",
            provider="openrouter",
            requested_model="hidden-model",
            reported_cost=Decimal("2.50"),
            currency="USD",
            outcome="success",
        )
    )
    await db_session.commit()
    monkeypatch.setenv("HITRENDY_ADMIN_IDENTITIES", "ops@example.com")

    outcome = await execute_reset(
        db_session,
        email="test@example.com",
        actor="ops@example.com",
        reason="prueba de soporte",
        confirm="RESET_USAGE",
    )

    assert outcome.ok
    assert outcome.workspaces_reset == 1
    assert await month_cost(db_session, workspace_id="ws_test_001") == Decimal("0")
    assert await db_session.scalar(select(UsageAdjustment)) is not None

    denied = await execute_reset(
        db_session,
        email="test@example.com",
        actor="no-autorizado@example.com",
        reason="no debe pasar",
        confirm="RESET_USAGE",
    )
    assert denied.result == "denied:not_authorized"


def test_monitoring_exposes_a_bounded_error_alert(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = MetricsRegistry()
    monkeypatch.setattr(settings, "alert_error_rate_percent", 50)
    registry.record_request(status_code=500, duration_ms=12, error_code="INTERNAL_ERROR")
    registry.record_request(status_code=200, duration_ms=8)

    snapshot = registry.snapshot()
    assert snapshot.alerts == ["error_rate_high"]
    exposition = registry.prometheus()
    assert "hitrendy_http_error_rate_percent 50.00" in exposition
    assert 'hitrendy_alert{name="error_rate_high"} 1' in exposition
