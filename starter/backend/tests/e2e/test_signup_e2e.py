from __future__ import annotations

import uuid

import pytest

from app.core.config import settings
from app.core.cookies import SIGNUP_COOKIE as SIGNUP_COOKIE_NAME


@pytest.mark.asyncio
async def test_pending_signup_completes_over_http_and_replays_idempotently(client_factory) -> None:
    client, _ = await client_factory(name="Signup E2E")
    client.cookies.delete(settings.session_cookie_name)
    email = f"signup-{uuid.uuid4().hex}@example.com"
    start = await client.post(
        "/api/v1/auth/signup/start",
        json={
            "email": email,
            "name": "Ana E2E",
            "password": "una-clave-e2e-segura-123",
            "interface_locale": "es",
        },
    )
    assert start.status_code == 201, start.text
    signup_token = start.cookies.get(SIGNUP_COOKIE_NAME)
    assert signup_token
    version = start.json()["signup"]["version"]
    for step, payload in (
        (
            "business",
            {
                "name": "Negocio Signup E2E",
                "category": "gastronomy",
                "country": "Honduras",
                "city": "Tegucigalpa",
                "primary_product": "Café E2E",
                "target_audience": "Personas de la ciudad",
            },
        ),
        (
            "channels",
            {"preferred_platforms": ["instagram"], "primary_objective": "sales"},
        ),
        (
            "brand",
            {
                "voice_tones": ["friendly"],
                "value_proposition": "Una propuesta E2E comprobable.",
                "preferred_words": ["artesanal"],
                "forbidden_words": ["barato"],
                "content_locale": "es",
            },
        ),
        ("review", {"confirmed": True}),
    ):
        saved = await client.patch(
            "/api/v1/auth/signup",
            json={"step": step, "expected_version": version, step: payload},
        )
        assert saved.status_code == 200, saved.text
        version = saved.json()["signup"]["version"]

    headers = {"Idempotency-Key": "signup-e2e-complete"}
    complete = await client.post("/api/v1/auth/signup/complete", headers=headers)
    assert complete.status_code == 200, complete.text
    payload = complete.json()
    assert payload["user"]["email"] == email
    assert payload["workspace"]["id"] == payload["business"]["workspace_id"]
    assert payload["brand_profile"]["business_id"] == payload["business"]["id"]
    assert (await client.get("/api/v1/auth/me")).status_code == 200

    client.cookies.set(SIGNUP_COOKIE_NAME, signup_token)
    replay = await client.post("/api/v1/auth/signup/complete", headers=headers)
    assert replay.status_code == 200
    assert replay.json() == payload
