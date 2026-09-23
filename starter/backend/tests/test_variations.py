from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

BUSINESS_DATA = {
    "name": "Café del Valle",
    "category": "gastronomy",
    "country": "México",
    "city": "Ciudad de México",
    "primary_product": "Café de especialidad",
    "target_audience": "Jóvenes profesionales de 25 a 40 años en CDMX",
    "preferred_platforms": ["instagram", "tiktok"],
    "primary_objective": "reach",
}

BRAND_DATA = {
    "voice_tones": ["friendly", "professional"],
    "value_proposition": "Café artesanal de origen responsable.",
    "preferred_words": ["artesanal", "origen"],
    "forbidden_words": ["barato"],
    "primary_color": "#541787",
    "secondary_color": "#B79CFA",
}

WORKSPACE_ID = "ws_test_001"


@pytest_asyncio.fixture
async def business_id(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    data = resp.json()
    await client.put(
        f"/api/v1/businesses/{data['id']}/brand-profile",
        json=BRAND_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    return data["id"]


@pytest_asyncio.fixture
async def conversation_id(client: AsyncClient, business_id: str) -> str:
    resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Test variaciones"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    return resp.json()["id"]


@pytest_asyncio.fixture
async def artifact_id(client: AsyncClient, conversation_id: str) -> str:
    msg_resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"text": "Crea un post promocional"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    data = msg_resp.json()
    assert data["type"] == "artifact"
    return data["artifact_id"]


@pytest.mark.asyncio
async def test_create_variation_shorter(
    client: AsyncClient, conversation_id: str, artifact_id: str
) -> None:
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations",
        json={"kind": "shorter"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "artifact"
    assert data["artifact_id"] == artifact_id
    assert "version_number" in data
    assert data["version_number"] == 2
    assert len(data["artifact"]["caption"]) < 180


@pytest.mark.asyncio
async def test_variation_reuses_idempotency_key_without_new_version(
    client: AsyncClient, conversation_id: str, artifact_id: str
) -> None:
    path = f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "variation-once"}
    first = await client.post(path, json={"kind": "shorter"}, headers=headers)
    second = await client.post(path, json={"kind": "shorter"}, headers=headers)
    conflict = await client.post(path, json={"kind": "more_youthful"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_create_variation_more_youthful(
    client: AsyncClient, conversation_id: str, artifact_id: str
) -> None:
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations",
        json={"kind": "more_youthful"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "artifact"
    assert "🔥" in data["artifact"]["hook"]


@pytest.mark.asyncio
async def test_create_variation_more_professional_and_friendly(
    client: AsyncClient, conversation_id: str, artifact_id: str
) -> None:
    professional = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations",
        json={"kind": "more_professional"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert professional.status_code == 200
    assert professional.json()["artifact"]["hook"].endswith("Café del Valle")

    friendly = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations",
        json={"kind": "more_friendly"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert friendly.status_code == 200
    assert friendly.json()["artifact"]["hook"] == "¡Tenemos algo especial para ti! 🎉"


@pytest.mark.asyncio
async def test_variation_rejected_wrong_workspace(
    client: AsyncClient, conversation_id: str, artifact_id: str
) -> None:
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations",
        json={"kind": "shorter"},
        headers={"X-Workspace-Id": "ws_other"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_variation_nonexistent_artifact(client: AsyncClient, conversation_id: str) -> None:
    resp = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/nonexistent_id/variations",
        json={"kind": "shorter"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_artifact_version(
    client: AsyncClient, conversation_id: str, artifact_id: str
) -> None:
    create_resp = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = create_resp.json()["id"]

    update_resp = await client.put(
        f"/api/v1/projects/{project_id}/artifact-version",
        json={
            "hook": "Hook editado",
            "caption": "Texto editado por el usuario.",
            "call_to_action": "Compra ahora",
            "hashtags": ["#Editado"],
            "visual_direction": "Imagen clara.",
            "format_recommendation": "static_post",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["version"]["hook"] == "Hook editado"
    assert data["version_number"] == 2
