from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _create_context(client: AsyncClient, workspace_id: str, name: str) -> str:
    business = await client.post(
        "/api/v1/businesses",
        json={
            "name": name,
            "category": "services",
            "country": "Honduras",
            "city": "Tegucigalpa",
            "primary_product": f"Servicio {name}",
            "target_audience": "Clientes E2E",
            "preferred_platforms": ["instagram"],
            "primary_objective": "reach",
        },
        headers={"X-Workspace-Id": workspace_id},
    )
    business_id = business.json()["id"]
    await client.put(
        f"/api/v1/businesses/{business_id}/brand-profile",
        json={"voice_tones": ["friendly"], "value_proposition": "Servicio E2E."},
        headers={"X-Workspace-Id": workspace_id},
    )
    conversation = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": f"{name} conversation"},
        headers={"X-Workspace-Id": workspace_id},
    )
    return conversation.json()["id"]


@pytest.mark.asyncio
async def test_same_key_is_isolated_between_workspaces(
    business_context, client_factory, fake_provider, generation_payload
) -> None:
    first_client: AsyncClient = business_context["client"]
    first_workspace = business_context["workspace_id"]
    second_client, second_workspace = await client_factory(name="Second E2E User")
    second_conversation = await _create_context(second_client, second_workspace, "Segundo")
    key = "e2e-shared-key"

    first = await first_client.post(
        f"/api/v1/conversations/{business_context['conversation_id']}/messages",
        json=generation_payload,
        headers={"X-Workspace-Id": first_workspace, "Idempotency-Key": key},
    )
    second = await second_client.post(
        f"/api/v1/conversations/{second_conversation}/messages",
        json=generation_payload,
        headers={"X-Workspace-Id": second_workspace, "Idempotency-Key": key},
    )
    forbidden = await second_client.get(
        f"/api/v1/conversations/{business_context['conversation_id']}",
        headers={"X-Workspace-Id": second_workspace},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["artifact_id"] != second.json()["artifact_id"]
    assert fake_provider.calls == 2
    assert forbidden.status_code == 404
