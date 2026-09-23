from __future__ import annotations

import asyncio
import io
from base64 import b64decode

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
PNG_1X1 = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
)


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


@pytest.mark.asyncio
async def test_create_conversation(client: AsyncClient, business_id: str) -> None:
    resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Promoción café frío"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "Promoción café frío"
    assert data["business_id"] == business_id
    assert "id" in data


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient, business_id: str) -> None:
    first = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Conversación 1"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Conversación 2"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    resp = await client.get(
        "/api/v1/conversations",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 2
    first_id = first.json()["id"]
    await client.post(
        f"/api/v1/conversations/{first_id}/messages",
        json={"text": "Mensaje que debe aparecer en el historial"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    response = await client.get("/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID})
    row = next(item for item in response.json() if item["id"] == first_id)
    assert row["last_message"] == "Mensaje que debe aparecer en el historial"


@pytest.mark.asyncio
async def test_send_message_generates_artifact(client: AsyncClient, business_id: str) -> None:
    conv_resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Test generación"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conv_id = conv_resp.json()["id"]

    msg_resp = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Quiero promocionar un café frío para esta semana"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert msg_resp.status_code == 200
    data = msg_resp.json()
    assert data["type"] == "artifact"
    assert "artifact" in data
    assert data["artifact"]["platform"] in ("instagram", "tiktok")
    assert len(data["artifact"]["hashtags"]) <= 5
    feedback = await client.post(
        f"/api/v1/conversations/artifacts/{data['artifact_id']}/feedback",
        json={"rating": "useful"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert feedback.status_code == 201
    assert feedback.json()["rating"] == "useful"
    event = await client.post(
        f"/api/v1/conversations/artifacts/{data['artifact_id']}/events",
        json={"event_type": "copied"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert event.status_code == 201
    assert event.json()["event_type"] == "copied"


@pytest.mark.asyncio
async def test_generation_reuses_a_completed_idempotency_key(
    client: AsyncClient, business_id: str
) -> None:
    conversation = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Idempotencia"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    path = f"/api/v1/conversations/{conversation.json()['id']}/messages"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "generation-once"}
    first = await client.post(path, json={"text": "Crea una publicación"}, headers=headers)
    second = await client.post(path, json={"text": "Crea una publicación"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_generation_rejects_same_key_with_different_payload(
    client: AsyncClient, business_id: str
) -> None:
    conversation = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Conflicto de idempotencia"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    path = f"/api/v1/conversations/{conversation.json()['id']}/messages"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "same-key"}
    first = await client.post(path, json={"text": "Crea un post"}, headers=headers)
    second = await client.post(path, json={"text": "Crea otro post"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"
    assert second.json()["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_simultaneous_generation_with_same_key_does_not_duplicate_artifact(
    client: AsyncClient, business_id: str
) -> None:
    conversation = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Concurrencia"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    path = f"/api/v1/conversations/{conversation.json()['id']}/messages"
    headers = {"X-Workspace-Id": WORKSPACE_ID, "Idempotency-Key": "race-key"}

    responses = await asyncio.gather(
        client.post(path, json={"text": "Crea una publicación"}, headers=headers),
        client.post(path, json={"text": "Crea una publicación"}, headers=headers),
    )

    assert sorted(response.status_code for response in responses) in ([200, 200], [200, 409])
    detail = await client.get(path.rsplit("/messages", 1)[0], headers={"X-Workspace-Id": WORKSPACE_ID})
    assert len(detail.json()["messages"]) == 2


@pytest.mark.asyncio
async def test_send_message_generates_short_video_script(
    client: AsyncClient, business_id: str
) -> None:
    conv_resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Guion para video"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conv_id = conv_resp.json()["id"]

    response = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={
            "text": "Crea un guion de video para presentar el café frío",
            "ui_intent": "create_short_video_script",
            "platform": "tiktok",
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    assert response.status_code == 200
    artifact = response.json()["artifact"]
    assert artifact["artifact_type"] == "short_video_script"
    assert artifact["platform"] == "tiktok"
    assert len(artifact["scenes"]) >= 2
    assert artifact["scenes"][0]["order"] == 1


@pytest.mark.asyncio
async def test_send_message_analyzes_an_authorized_visual_asset(
    client: AsyncClient, business_id: str
) -> None:
    upload = await client.post("/api/v1/assets/uploads", headers={"X-Workspace-Id": WORKSPACE_ID})
    completed = await client.post(
        f"/api/v1/assets/uploads/{upload.json()['upload_id']}/complete",
        files={"file": ("design.png", io.BytesIO(PNG_1X1), "image/png")},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conv = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Revisión visual"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    response = await client.post(
        f"/api/v1/conversations/{conv.json()['id']}/messages",
        json={
            "text": "Revisa este diseño",
            "ui_intent": "analyze_visual",
            "attachment_ids": [completed.json()["asset_id"]],
        },
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "visual_analysis"
    assert data["analysis"]["asset_id"] == completed.json()["asset_id"]
    assert data["analysis"]["strengths"]


@pytest.mark.asyncio
async def test_send_message_rejects_unimplemented_intent_and_attachments(
    client: AsyncClient, business_id: str
) -> None:
    conv_resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Límites del asistente"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conv_id = conv_resp.json()["id"]

    unsupported = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Dame una campaña", "ui_intent": "create_campaign_idea"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert unsupported.status_code == 422

    attachments = await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Analiza esto", "attachment_ids": ["asset_001"]},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert attachments.status_code == 422


@pytest.mark.asyncio
async def test_get_conversation_with_messages(client: AsyncClient, business_id: str) -> None:
    conv_resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Con mensajes"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conv_id = conv_resp.json()["id"]

    await client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"text": "Crea un post"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )

    resp = await client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    assert data["messages"][1]["artifact_id"]
    assert data["messages"][1]["artifact"]["artifact_type"] == "social_post"


@pytest.mark.asyncio
async def test_conversation_access_rejected_wrong_workspace(
    client: AsyncClient, business_id: str
) -> None:
    conv_resp = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Privada"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conv_id = conv_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/conversations/{conv_id}",
        headers={"X-Workspace-Id": "ws_other"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_archive_and_restore_conversation(client: AsyncClient, business_id: str) -> None:
    created = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Para archivar"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    conversation_id = created.json()["id"]

    archived = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"status": "archived"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    archived_detail = await client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert archived_detail.status_code == 200
    assert archived_detail.json()["status"] == "archived"

    message_response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"text": "No debe generar contenido"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert message_response.status_code == 422

    active = await client.get("/api/v1/conversations", headers={"X-Workspace-Id": WORKSPACE_ID})
    assert conversation_id not in {item["id"] for item in active.json()}
    archived_list = await client.get(
        "/api/v1/conversations?status=archived", headers={"X-Workspace-Id": WORKSPACE_ID}
    )
    assert conversation_id in {item["id"] for item in archived_list.json()}

    restored = await client.patch(
        f"/api/v1/conversations/{conversation_id}",
        json={"status": "active"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    assert restored.status_code == 200
    assert restored.json()["status"] == "active"


@pytest.mark.asyncio
async def test_archive_rejects_wrong_workspace(client: AsyncClient, business_id: str) -> None:
    created = await client.post(
        "/api/v1/conversations",
        json={"business_id": business_id, "title": "Privada"},
        headers={"X-Workspace-Id": WORKSPACE_ID},
    )
    response = await client.patch(
        f"/api/v1/conversations/{created.json()['id']}",
        json={"status": "archived"},
        headers={"X-Workspace-Id": "ws_other"},
    )
    assert response.status_code == 403
