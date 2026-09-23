from __future__ import annotations

import pytest
from httpx import AsyncClient

BUSINESS_DATA = {
    "name": "Café del Valle",
    "category": "gastronomy",
    "country": "México",
    "city": "Ciudad de México",
    "description": "Cafetería artesanal en Coyoacán.",
    "primary_product": "Café de especialidad",
    "target_audience": "Jóvenes profesionales de 25 a 40 años en CDMX",
    "preferred_platforms": ["instagram", "tiktok"],
    "primary_objective": "reach",
}

WORKSPACE_ID = "ws_test_001"
OTHER_WORKSPACE = "ws_other_002"


@pytest.mark.asyncio
async def test_create_business(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Café del Valle"
    assert data["workspace_id"] == WORKSPACE_ID
    assert data["preferred_platforms"] == ["instagram", "tiktok"]
    assert "id" in data


@pytest.mark.asyncio
async def test_create_business_missing_required_field(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/businesses",
        json={"name": "Test"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_business(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    biz_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/businesses/{biz_id}",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Café del Valle"


@pytest.mark.asyncio
async def test_get_business_cross_workspace_rejected(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    biz_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/businesses/{biz_id}",
        headers={"X-Workspace-Id": OTHER_WORKSPACE},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_business(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    biz_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/businesses/{biz_id}",
        json={"name": "Café del Valle Premium"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Café del Valle Premium"


@pytest.mark.asyncio
async def test_upsert_brand_profile(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    biz_id = create_resp.json()["id"]

    brand_data = {
        "voice_tones": ["friendly", "professional"],
        "value_proposition": "Café artesanal de origen responsable.",
        "preferred_words": ["artesanal", "origen"],
        "forbidden_words": ["barato"],
        "primary_color": "#541787",
        "secondary_color": "#B79CFA",
    }
    resp = await client.put(
        f"/api/v1/businesses/{biz_id}/brand-profile",
        json=brand_data,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["voice_tones"] == ["friendly", "professional"]
    assert data["value_proposition"] == "Café artesanal de origen responsable."
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_get_brand_profile(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/api/v1/businesses",
        json=BUSINESS_DATA,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    biz_id = create_resp.json()["id"]

    brand_data = {
        "voice_tones": ["friendly"],
        "value_proposition": "Calidad artesanal.",
        "preferred_words": [],
        "forbidden_words": [],
    }
    await client.put(
        f"/api/v1/businesses/{biz_id}/brand-profile",
        json=brand_data,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    resp = await client.get(
        f"/api/v1/businesses/{biz_id}/brand-profile",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["value_proposition"] == "Calidad artesanal."
