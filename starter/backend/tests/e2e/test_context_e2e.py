from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_identity_workspace_and_conversation_are_authorized(
    business_context, client_factory
) -> None:
    context = business_context
    client: AsyncClient = context["client"]
    workspace_id = context["workspace_id"]

    me = await client.get("/api/v1/auth/me")
    conversation = await client.get(
        f"/api/v1/conversations/{context['conversation_id']}",
        headers={"X-Workspace-Id": workspace_id},
    )
    other_client, other_workspace_id = await client_factory(name="Other E2E User")
    cross_workspace = await other_client.get(
        f"/api/v1/conversations/{context['conversation_id']}",
        headers={"X-Workspace-Id": other_workspace_id},
    )

    assert me.status_code == 200
    assert me.json()["workspaces"][0]["id"] == workspace_id
    assert conversation.status_code == 200
    assert conversation.json()["id"] == context["conversation_id"]
    assert conversation.json()["business_id"] == context["business"]["id"]
    assert cross_workspace.status_code == 404
