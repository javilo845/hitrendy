from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.conversations.models import GeneratedArtifact


@pytest.mark.asyncio
async def test_instagram_post_flow_is_persistent_editable_and_idempotent(
    business_context, fake_provider
) -> None:
    client = business_context["client"]
    workspace_id = business_context["workspace_id"]
    business = business_context["business"]
    conversation_id = business_context["conversation_id"]
    headers = {"X-Workspace-Id": workspace_id, "Idempotency-Key": "instagram-flow-generate"}

    templates = await client.get("/api/v1/templates?platform=instagram&format=static_post")
    assert templates.status_code == 200
    selected = templates.json()[0]
    assert selected["aspect_ratio"] == "4:5"
    assert selected["canva_url"].startswith("https://canva.link/")

    flow_headers = {"Idempotency-Key": "instagram-flow-start"}
    started = await client.post("/api/v1/projects/flow-events", json={"business_id": business["id"]}, headers=flow_headers)
    started_replay = await client.post("/api/v1/projects/flow-events", json={"business_id": business["id"]}, headers=flow_headers)
    assert started.status_code == started_replay.status_code == 201
    assert started.json() == started_replay.json()
    generated = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "text": "Presenta nuestro café artesanal sin usar palabras prohibidas.",
            "platform": "instagram",
            "objective": "sales",
            "quality_level": "fast",
            "locale": "pt",
        },
    )
    replay = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={
            "text": "Presenta nuestro café artesanal sin usar palabras prohibidas.",
            "platform": "instagram",
            "objective": "sales",
            "quality_level": "fast",
            "locale": "pt",
        },
    )
    assert generated.status_code == replay.status_code == 200
    assert generated.json() == replay.json()
    assert fake_provider.calls == 1
    assert fake_provider.last_social_request is not None
    assert fake_provider.last_social_request.locale == "pt"
    assert fake_provider.last_social_request.business.value_proposition == "Una propuesta E2E comprobable."
    post = generated.json()["artifact"]
    assert post["platform"] == "instagram"
    assert "barato" not in str(post).casefold()
    assert "4:5" in post["visual_direction"]

    artifact_id = generated.json()["artifact_id"]
    save_headers = {"Idempotency-Key": "instagram-flow-save"}
    project = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id, "template_id": selected["id"]},
        headers=save_headers,
    )
    project_replay = await client.post(
        "/api/v1/projects",
        json={"artifact_id": artifact_id, "template_id": selected["id"]},
        headers=save_headers,
    )
    assert project.status_code == 201
    assert project.json() == project_replay.json()
    project_id = project.json()["id"]
    edited = await client.put(
        f"/api/v1/projects/{project_id}/artifact-version",
        json={**post, "caption": "Conteúdo editado para o café artesanal.", "visual_direction": "Brief visual 4:5 para Canva, café em destaque."},
    )
    assert edited.status_code == 200
    reloaded = await client.get(f"/api/v1/projects/{project_id}")
    assert reloaded.json()["artifact_snapshot"]["caption"] == "Conteúdo editado para o café artesanal."
    assert reloaded.json()["source_template_id"] == selected["id"]
    assert reloaded.json()["artifact_id"] == artifact_id

    duplicated = await client.post(
        f"/api/v1/projects/{project_id}/duplicate", headers={"Idempotency-Key": "instagram-flow-duplicate"}
    )
    duplicate_replay = await client.post(
        f"/api/v1/projects/{project_id}/duplicate", headers={"Idempotency-Key": "instagram-flow-duplicate"}
    )
    assert duplicated.status_code == duplicate_replay.status_code == 201
    assert duplicated.json() == duplicate_replay.json()
    assert duplicated.json()["artifact_id"] != artifact_id

    variation = await client.post(
        f"/api/v1/conversations/{conversation_id}/artifacts/{artifact_id}/variations",
        json={"kind": "more_friendly"}, headers={"Idempotency-Key": "instagram-flow-variation"},
    )
    assert variation.status_code == 200
    assert variation.json()["version_number"] >= 3
    completed = await client.patch(
        f"/api/v1/projects/flow-events/{started.json()['id']}", json={"status": "completed"}
    )
    assert completed.status_code == 200
    assert completed.json()["completion_status"] == "completed"
    assert completed.json()["elapsed_seconds"] is not None

    from app.dependencies import get_db
    provider = client._transport.app.dependency_overrides[get_db]()  # type: ignore[attr-defined]
    session = await anext(provider)
    try:
        count = await session.scalar(
            select(func.count()).select_from(GeneratedArtifact).where(
                GeneratedArtifact.conversation_id == conversation_id
            )
        )
        assert count == 2  # original plus duplicate; the variation is a version.
    finally:
        await provider.aclose()
