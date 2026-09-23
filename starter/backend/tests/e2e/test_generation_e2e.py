from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_generation_persists_messages_and_artifact(
    business_context, fake_provider, generation_payload
) -> None:
    client: AsyncClient = business_context["client"]
    workspace_id = business_context["workspace_id"]
    conversation_id = business_context["conversation_id"]

    templates = await client.get("/api/v1/templates")
    template = templates.json()[0]
    assert (await client.get(f"/api/v1/templates/{template['id']}")).json() == template

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=generation_payload,
        headers={
            "X-Workspace-Id": workspace_id,
            "Idempotency-Key": "e2e-generation-once",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["type"] == "artifact"
    assert result["artifact"]["artifact_type"] == "social_post"
    assert result["artifact_id"]
    assert fake_provider.calls == 1

    reopened = await client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers={"X-Workspace-Id": workspace_id},
    )
    assert reopened.status_code == 200
    messages = reopened.json()["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[1]["artifact_id"] == result["artifact_id"]
    assert messages[1]["artifact"] == result["artifact"]
    assert messages[1]["content"] == result["assistant_message"]["content"]
