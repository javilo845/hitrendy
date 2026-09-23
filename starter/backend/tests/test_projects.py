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
        json={"business_id": business_id, "title": "Test proyectos"},
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
    assert data["artifact_id"] is not None
    return data["artifact_id"]


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, artifact_id: str) -> None:
    resp = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"]
    assert data["artifact_id"] == artifact_id
    assert data["status"] == "active"
    assert "artifact_snapshot" in data


@pytest.mark.asyncio
async def test_create_project_from_artifact_is_idempotent_and_does_not_reassign(
    client: AsyncClient, artifact_id: str
) -> None:
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "project-save-once"}
    payload = {"artifact_id": artifact_id}
    first = await client.post("/api/v1/projects", json=payload, headers=headers)
    replay = await client.post("/api/v1/projects", json=payload, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    projects = await client.get("/api/v1/projects", headers={"X-Workspace-Id": WORKSPACE_ID})
    assert len([item for item in projects.json() if item["artifact_id"] == artifact_id]) == 1

    conflict = await client.post(
        "/api/v1/projects", json={"artifact_id": artifact_id, "name": "Otro"}, headers=headers
    )
    assert conflict.status_code == 409
    reassignment = await client.post(
        "/api/v1/projects",
        json=payload,
        headers={"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "project-save-other-key"},
    )
    assert reassignment.status_code == 409


@pytest.mark.asyncio
async def test_failed_project_save_is_retryable_and_does_not_leave_processing(client: AsyncClient) -> None:
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "failed-project-save"}
    first = await client.post("/api/v1/projects", json={"artifact_id": "missing"}, headers=headers)
    retry = await client.post("/api/v1/projects", json={"artifact_id": "missing"}, headers=headers)
    assert first.status_code == retry.status_code == 404


@pytest.mark.asyncio
async def test_video_script_project_can_be_edited_and_versioned(
    client: AsyncClient, conversation_id: str
) -> None:
    generated = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={
            "text": "Crea un guion de video sobre el café de especialidad",
            "ui_intent": "create_short_video_script",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    artifact_id = generated.json()["artifact_id"]
    created = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    script = created.json()["artifact_snapshot"]
    assert script["artifact_type"] == "short_video_script"

    script["hook"] = "Un café que transforma tu pausa"
    saved = await client.put(
        f"/api/v1/projects/{project_id}/artifact-version",
        json=script,
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert saved.status_code == 200
    assert saved.json()["version_number"] == 2
    assert saved.json()["version"]["hook"] == "Un café que transforma tu pausa"
    assert saved.json()["edit_magnitude_percent"] > 0


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, artifact_id: str) -> None:
    await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    resp = await client.get(
        "/api/v1/projects",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) >= 1
    assert all(p["workspace_id"] == WORKSPACE_ID for p in projects)


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, artifact_id: str) -> None:
    create_resp = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = create_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project_id}",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == project_id
    assert "artifact_snapshot" in data


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, artifact_id: str) -> None:
    create_resp = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Mi proyecto renombrado", "status": "archived"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Mi proyecto renombrado"
    assert data["status"] == "archived"


@pytest.mark.asyncio
async def test_create_project_from_nonexistent_artifact(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/projects",
        json={"artifact_id": "nonexistent_id"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_project_from_canva_catalog_template_is_refused_clearly(
    client: AsyncClient,
) -> None:
    """A browse-only catalogue id must not be answered with "no existe".

    ``GET /templates`` lists these entries and ``GET /templates/{id}`` resolves
    them, so a 404 here would contradict the two endpoints that handed the id
    out. They carry no editable slots, which is the actual reason a project
    cannot start from one.
    """
    listed = await client.get("/api/v1/templates")
    catalog = [item for item in listed.json() if item["source"] == "canva"]
    assert catalog, "el catálogo de Canva debería estar en la lista"

    resp = await client.post(
        "/api/v1/projects",
        json={"template_id": catalog[0]["id"], "business_id": "biz_demo"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    assert resp.status_code == 422
    assert "Canva" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_project_isolation_by_workspace(client: AsyncClient, artifact_id: str) -> None:
    create_resp = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = create_resp.json()["id"]

    # Other workspace should not see this project
    resp = await client.get(
        f"/api/v1/projects/{project_id}",
        headers={"X-Workspace-Id": "ws_other"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_duplicate_project_is_workspace_scoped(client: AsyncClient, artifact_id: str) -> None:
    created = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = created.json()["id"]
    copied = await client.post(
        f"/api/v1/projects/{project_id}/duplicate", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    assert copied.status_code == 201
    assert copied.json()["id"] != project_id
    assert copied.json()["name"].endswith("(copia)")
    assert copied.json()["artifact_id"] != created.json()["artifact_id"]

    update_copy = await client.put(
        f"/api/v1/projects/{copied.json()['id']}/artifact-version",
        json={
            "hook": "Gancho de la copia",
            "caption": "Texto independiente de la copia.",
            "call_to_action": "Escríbenos hoy.",
            "hashtags": ["#HiTrendy"],
            "visual_direction": "Producto en primer plano.",
            "format_recommendation": "static_post",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert update_copy.status_code == 200
    original = await client.get(
        f"/api/v1/projects/{project_id}", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    assert original.json()["artifact_snapshot"]["hook"] != "Gancho de la copia"
    forbidden = await client.post(
        f"/api/v1/projects/{project_id}/duplicate", headers={"X-Workspace-Id": "ws_other"}
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_failed_duplicate_is_retryable_without_a_partial_project(client: AsyncClient) -> None:
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "failed-duplicate"}
    first = await client.post("/api/v1/projects/missing/duplicate", headers=headers)
    replay = await client.post("/api/v1/projects/missing/duplicate", headers=headers)
    assert first.status_code == replay.status_code == 404


@pytest.mark.asyncio
async def test_export_project_is_workspace_scoped(client: AsyncClient, artifact_id: str) -> None:
    created = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = created.json()["id"]
    exported = await client.get(
        f"/api/v1/projects/{project_id}/export", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    assert exported.status_code == 200
    assert exported.json()["format"] == "hitrendy-project/v1"
    assert exported.json()["project"]["content"]
    forbidden = await client.get(
        f"/api/v1/projects/{project_id}/export", headers={"X-Workspace-Id": "ws_other"}
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_list_project_versions(client: AsyncClient, artifact_id: str) -> None:
    created = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    response = await client.get(
        f"/api/v1/projects/{created.json()['id']}/versions",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert response.status_code == 200
    assert response.json()[0]["version_number"] == 1


@pytest.mark.asyncio
async def test_restore_project_version_creates_a_new_current_version(
    client: AsyncClient, artifact_id: str
) -> None:
    created = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = created.json()["id"]
    original_hook = created.json()["artifact_snapshot"]["hook"]
    update = await client.put(
        f"/api/v1/projects/{project_id}/artifact-version",
        json={
            "hook": "Un gancho editado",
            "caption": "Un texto editado para el proyecto.",
            "call_to_action": "Escríbenos hoy.",
            "hashtags": ["#HiTrendy"],
            "visual_direction": "Producto en primer plano.",
            "format_recommendation": "static_post",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert update.status_code == 200
    versions = await client.get(
        f"/api/v1/projects/{project_id}/versions", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    original_version = next(v for v in versions.json() if v["version_number"] == 1)

    restored = await client.post(
        f"/api/v1/projects/{project_id}/versions/{original_version['id']}/restore",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    assert restored.status_code == 200
    assert restored.json()["version_number"] == 3
    assert restored.json()["restored_from_version"] == 1
    project = await client.get(
        f"/api/v1/projects/{project_id}", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    assert project.json()["artifact_snapshot"]["hook"] == original_hook
    version_numbers = [
        version["version_number"]
        for version in (
            await client.get(
                f"/api/v1/projects/{project_id}/versions",
                headers={"X-Workspace-Id": WORKSPACE_ID},
            )
        ).json()
    ]
    assert version_numbers == [3, 2, 1]


@pytest.mark.asyncio
async def test_restore_project_version_is_workspace_scoped(
    client: AsyncClient, artifact_id: str
) -> None:
    created = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    project_id = created.json()["id"]
    version = (
        await client.get(
            f"/api/v1/projects/{project_id}/versions",
            headers={"X-Workspace-Id": WORKSPACE_ID},
        )
    ).json()[0]

    forbidden = await client.post(
        f"/api/v1/projects/{project_id}/versions/{version['id']}/restore",
        headers={"X-Workspace-Id": "ws_other"},
    )

    assert forbidden.status_code == 403
