from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text


def _database_status(migrated_database, key: str, workspace_id: str) -> str:
    with migrated_database.connect() as connection:
        return connection.scalar(
            text(
                "SELECT status FROM idempotency_records "
                "WHERE key = :key AND workspace_id = :workspace_id"
            ),
            {"key": key, "workspace_id": workspace_id},
        )


@pytest.mark.asyncio
async def test_recoverable_provider_error_can_retry_same_operation(
    business_context, fake_provider, generation_payload, migrated_database
) -> None:
    client: AsyncClient = business_context["client"]
    key = "e2e-recoverable-error"
    fake_provider.transient_failures = 1

    failed = await client.post(
        f"/api/v1/conversations/{business_context['conversation_id']}/messages",
        json=generation_payload,
        headers={"X-Workspace-Id": business_context["workspace_id"], "Idempotency-Key": key},
    )
    retried = await client.post(
        f"/api/v1/conversations/{business_context['conversation_id']}/messages",
        json=generation_payload,
        headers={"X-Workspace-Id": business_context["workspace_id"], "Idempotency-Key": key},
    )
    thread = await client.get(
        f"/api/v1/conversations/{business_context['conversation_id']}",
        headers={"X-Workspace-Id": business_context["workspace_id"]},
    )

    assert failed.status_code == 503
    assert failed.json()["error"]["retryable"] is True
    assert _database_status(migrated_database, key, business_context["workspace_id"]) == "completed"
    assert retried.status_code == 200
    assert fake_provider.calls == 2
    assert len(thread.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_permanent_provider_error_has_no_partial_artifact(
    business_context, fake_provider, generation_payload, migrated_database
) -> None:
    client: AsyncClient = business_context["client"]
    key = "e2e-permanent-error"
    fake_provider.permanent_failure = True

    response = await client.post(
        f"/api/v1/conversations/{business_context['conversation_id']}/messages",
        json=generation_payload,
        headers={"X-Workspace-Id": business_context["workspace_id"], "Idempotency-Key": key},
    )
    thread = await client.get(
        f"/api/v1/conversations/{business_context['conversation_id']}",
        headers={"X-Workspace-Id": business_context["workspace_id"]},
    )

    assert response.status_code == 502
    assert response.json()["error"]["retryable"] is False
    assert _database_status(migrated_database, key, business_context["workspace_id"]) == "failed"
    assert len(thread.json()["messages"]) == 1
    assert fake_provider.calls == 1


@pytest.mark.asyncio
async def test_invalid_request_does_not_call_provider(business_context, fake_provider) -> None:
    client: AsyncClient = business_context["client"]
    response = await client.post(
        f"/api/v1/conversations/{business_context['conversation_id']}/messages",
        json={"text": ""},
        headers={"X-Workspace-Id": business_context["workspace_id"]},
    )

    assert response.status_code == 422
    assert fake_provider.calls == 0
