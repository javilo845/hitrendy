from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _message_url(context: dict[str, object]) -> str:
    return f"/api/v1/conversations/{context['conversation_id']}/messages"


def _headers(context: dict[str, object], key: str) -> dict[str, str]:
    return {"X-Workspace-Id": str(context["workspace_id"]), "Idempotency-Key": key}


@pytest.mark.asyncio
async def test_repeated_generation_returns_persisted_result_without_duplicates(
    business_context, fake_provider, generation_payload
) -> None:
    client: AsyncClient = business_context["client"]
    key = "e2e-idempotency-once"
    first = await client.post(
        _message_url(business_context),
        json=generation_payload,
        headers=_headers(business_context, key),
    )
    second = await client.post(
        _message_url(business_context),
        json=generation_payload,
        headers=_headers(business_context, key),
    )
    conflict = await client.post(
        _message_url(business_context),
        json={"text": "Crea una solicitud diferente"},
        headers=_headers(business_context, key),
    )
    thread = await client.get(
        f"/api/v1/conversations/{business_context['conversation_id']}",
        headers={"X-Workspace-Id": str(business_context["workspace_id"])},
    )

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["retryable"] is False
    assert fake_provider.calls == 1
    assert len(thread.json()["messages"]) == 2
    assert sum(message["role"] == "assistant" for message in thread.json()["messages"]) == 1


@pytest.mark.asyncio
async def test_concurrent_generation_reserves_one_operation(
    business_context, fake_provider, generation_payload
) -> None:
    client: AsyncClient = business_context["client"]
    fake_provider.delay_seconds = 0.05
    key = "e2e-concurrent-once"

    responses = await asyncio.gather(
        client.post(
            _message_url(business_context),
            json=generation_payload,
            headers=_headers(business_context, key),
        ),
        client.post(
            _message_url(business_context),
            json=generation_payload,
            headers=_headers(business_context, key),
        ),
    )
    thread = await client.get(
        f"/api/v1/conversations/{business_context['conversation_id']}",
        headers={"X-Workspace-Id": str(business_context["workspace_id"])},
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert fake_provider.calls == 1
    assert len(thread.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_idempotency_result_survives_new_http_session(
    business_context, fake_provider, generation_payload
) -> None:
    client: AsyncClient = business_context["client"]
    key = "e2e-restart-once"
    first = await client.post(
        _message_url(business_context),
        json=generation_payload,
        headers=_headers(business_context, key),
    )

    reopened_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reopened_client.cookies.update(client.cookies)
    try:
        replay = await reopened_client.post(
            _message_url(business_context),
            json=generation_payload,
            headers=_headers(business_context, key),
        )
    finally:
        await reopened_client.aclose()

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert fake_provider.calls == 1
