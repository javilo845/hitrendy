from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text


@pytest.mark.asyncio
async def test_health_and_migrated_postgres_are_ready(
    authenticated_client: tuple[AsyncClient, str], migrated_database
) -> None:
    client, _ = authenticated_client

    live = await client.get("/health/live")
    ready = await client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ok",
        "checks": {"database": "ok", "storage": "available", "redis": "available"},
    }
    with migrated_database.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "024"
