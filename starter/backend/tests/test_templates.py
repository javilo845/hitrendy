from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.templates.canva_catalog import CANVA_CATALOG
from app.templates.repository import SEED_TEMPLATES

WORKSPACE_ID = "ws_test_001"

TEMPLATE_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[3] / "contracts" / "schemas" / "template.schema.json"
    ).read_text(encoding="utf-8")
)

#: The 12 niches the web can draw a cover for.
COVER_TOKENS = {
    "technology", "gastronomy", "fashion", "beauty", "fitness", "health",
    "education", "real_estate", "automotive", "travel", "events", "pets",
}


def assert_matches_contract(template: dict) -> None:
    """Every listed template must satisfy the shape the web is built against."""
    assert set(template) <= set(TEMPLATE_SCHEMA["properties"])
    for key in TEMPLATE_SCHEMA["required"]:
        assert key in template, key
    assert template["source"] in {"custom", "canva"}
    assert template["cover"] is None or template["cover"] in COVER_TOKENS
    if template["source"] == "canva":
        assert template["thumbnail_url"] is None
        assert template["cover"] in COVER_TOKENS
        # Browse-only: nothing downstream can autofill a Canva listing.
        assert template["editable_slots"] == []
    else:
        assert template["thumbnail_url"]
        assert template["cover"] is None


@pytest.mark.asyncio
async def test_list_templates(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == len(SEED_TEMPLATES) + len(CANVA_CATALOG)
    assert all("id" in t for t in data)
    assert all("title" in t for t in data)
    # The fillable templates lead so the studio flow keeps picking one.
    assert [t["id"] for t in data[: len(SEED_TEMPLATES)]] == [t["id"] for t in SEED_TEMPLATES]
    for template in data:
        assert_matches_contract(template)


@pytest.mark.asyncio
async def test_seed_templates_is_idempotent(seeded_client: AsyncClient) -> None:
    first = await seeded_client.get(
        "/api/v1/templates",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    second = await seeded_client.get(
        "/api/v1/templates",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(second.json()) == len(SEED_TEMPLATES) + len(CANVA_CATALOG)


@pytest.mark.asyncio
async def test_list_templates_filter_by_platform(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates?platform=instagram",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for t in data:
        assert t["platforms"] == ["instagram"]
        if t["source"] == "custom":
            assert t["aspect_ratio"] == "4:5"
            assert t["canva_url"].startswith("https://canva.link/")
        else:
            assert t["canva_url"].startswith("https://www.canva.com/")


@pytest.mark.asyncio
async def test_list_templates_filter_by_category(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates?category=promotion",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for t in data:
        assert t["category"] == "promotion"


@pytest.mark.asyncio
async def test_list_templates_search(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates?search=producto",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any("Producto" in t["title"] for t in data)


@pytest.mark.asyncio
async def test_get_template(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates/tpl_instagram_01",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "tpl_instagram_01"
    assert data["title"] == "Producto destacado"
    assert data["platforms"] == ["instagram"]
    assert data["formats"] == ["static_post"]
    assert data["aspect_ratio"] == "4:5"


@pytest.mark.asyncio
async def test_get_template_not_found(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/templates/nonexistent",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_recommend_templates_returns_ranked_rationales(seeded_client: AsyncClient) -> None:
    response = await seeded_client.post(
        "/api/v1/templates/recommendations",
        json={"platform": "instagram", "objective": "sales", "category": "promotion"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert response.status_code == 200
    recommendations = response.json()
    assert recommendations
    assert recommendations[0]["score"] >= recommendations[-1]["score"]
    assert recommendations[0]["rationale"]


@pytest.mark.asyncio
async def test_create_project_from_template(seeded_client: AsyncClient) -> None:
    business_response = await seeded_client.post(
        "/api/v1/businesses",
        json={
            "name": "Café de prueba",
            "category": "gastronomy",
            "country": "Honduras",
            "city": "Tegucigalpa",
            "primary_product": "Café",
            "target_audience": "Clientes locales",
            "preferred_platforms": ["instagram"],
            "primary_objective": "sales",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    business_id = business_response.json()["id"]
    resp = await seeded_client.post(
        "/api/v1/projects",
        json={"template_id": "tpl_instagram_01", "business_id": business_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Producto destacado"
    assert data["platform"] == "instagram"
    assert data["status"] == "active"
    assert data["artifact_snapshot"] is not None
    assert data["source_template_id"] == "tpl_instagram_01"
    assert data["artifact_id"] is not None

    reopened = await seeded_client.get(
        f"/api/v1/projects/{data['id']}", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    assert reopened.status_code == 200
    snapshot = reopened.json()["artifact_snapshot"]
    assert snapshot["hook"] == "Producto destacado"

    edited = await seeded_client.put(
        f"/api/v1/projects/{data['id']}/artifact-version",
        json={
            **snapshot,
            "hook": "Un reel listo para editar",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert edited.status_code == 200
    assert edited.json()["version_number"] == 2


@pytest.mark.asyncio
async def test_list_templates_includes_canva_catalog(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    catalog = [t for t in resp.json() if t["source"] == "canva"]
    assert {t["id"] for t in catalog} == {t["id"] for t in CANVA_CATALOG}
    assert {t["cover"] for t in catalog} == COVER_TOKENS
    assert {t["formats"][0] for t in catalog} == {"static_post", "story"}


@pytest.mark.asyncio
async def test_list_templates_filters_apply_to_canva_catalog(
    seeded_client: AsyncClient,
) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates?format=story",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data
    # Only catalog entries carry the vertical format, so the seeds must drop out.
    assert all(t["source"] == "canva" for t in data)
    assert all(t["formats"] == ["story"] for t in data)
    assert all(t["aspect_ratio"] == "9:16" for t in data)

    filtered = await seeded_client.get(
        "/api/v1/templates?format=story&objective=engagement",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert filtered.status_code == 200
    assert {t["id"] for t in filtered.json()} == {"canva_fitness_story"}


@pytest.mark.asyncio
async def test_list_templates_search_matches_canva_catalog(
    seeded_client: AsyncClient,
) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates?search=MASCOTAS",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    assert {t["id"] for t in resp.json()} == {"canva_pets_post"}


@pytest.mark.asyncio
async def test_get_canva_template_resolves_from_catalog(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        "/api/v1/templates/canva_gastronomy_post",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "canva_gastronomy_post"
    assert data["source"] == "canva"
    assert data["cover"] == "gastronomy"
    assert data["thumbnail_url"] is None
    # /templates/?query= is the only form Canva actually searches. Its category
    # pages answer 200 for any ?query= and then ignore it -- they emit a
    # canonical tag without the parameter and return the same evergreen gallery
    # -- so a link built from one sends every recommendation to the same place.
    assert data["canva_url"].startswith("https://www.canva.com/templates/?query=")
    assert "instagram+post" in data["canva_url"]
    assert "restaurante" in data["canva_url"]
    assert_matches_contract(data)


@pytest.mark.asyncio
async def test_recommendations_exclude_canva_catalog(seeded_client: AsyncClient) -> None:
    response = await seeded_client.post(
        "/api/v1/templates/recommendations",
        json={"platform": "instagram", "objective": "sales", "limit": 6},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert response.status_code == 200
    recommendations = response.json()
    assert recommendations
    assert all(t["source"] == "custom" for t in recommendations)
    assert all(t["editable_slots"] for t in recommendations)
