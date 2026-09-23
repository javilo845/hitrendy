from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_variation_is_versioned_and_idempotent(
    business_context, fake_provider, generation_payload
) -> None:
    client: AsyncClient = business_context["client"]
    workspace_id = business_context["workspace_id"]
    conversation_id = business_context["conversation_id"]
    message = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=generation_payload,
        headers={"X-Workspace-Id": workspace_id, "Idempotency-Key": "variation-source"},
    )
    artifact_id = message.json()["artifact_id"]
    project = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": workspace_id},
    )
    project_id = project.json()["id"]
    path = f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations"
    headers = {"X-Workspace-Id": workspace_id, "Idempotency-Key": "variation-once"}

    first = await client.post(path, json={"kind": "shorter"}, headers=headers)
    second = await client.post(path, json={"kind": "shorter"}, headers=headers)
    conflict = await client.post(path, json={"kind": "more_youthful"}, headers=headers)
    versions = await client.get(
        f"/api/v1/projects/{project_id}/versions",
        headers={"X-Workspace-Id": workspace_id},
    )
    current_project = await client.get(
        f"/api/v1/projects/{project_id}",
        headers={"X-Workspace-Id": workspace_id},
    )

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert conflict.status_code == 409
    assert fake_provider.calls == 2
    assert [version["version_number"] for version in versions.json()] == [2, 1]
    assert current_project.json()["artifact_snapshot"] == first.json()["artifact"]
