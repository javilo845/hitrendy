from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command
from app.core.config import settings
from app.dependencies import get_db
from app.main import _rate_windows, app
from tests.e2e.fake_provider import DeterministicE2EProvider

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
_database_name = unquote(urlparse(TEST_DATABASE_URL).path.lstrip("/")).split("?", 1)[0]


def _validate_test_database_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"}:
        raise pytest.UsageError("TEST_DATABASE_URL debe usar PostgreSQL con psycopg.")
    if not parsed.hostname or not _database_name:
        raise pytest.UsageError("TEST_DATABASE_URL debe incluir host y base de datos.")
    if _database_name in {"hitrendy", "postgres"} or not _database_name.endswith(("_test", "_e2e")):
        raise pytest.UsageError(
            "TEST_DATABASE_URL debe apuntar a una base cuyo nombre termine en _test o _e2e; "
            "la base de desarrollo está bloqueada."
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    regular_items: list[pytest.Item] = []
    e2e_items: list[pytest.Item] = []
    for item in items:
        if "/tests/e2e/" not in str(item.fspath):
            regular_items.append(item)
            continue
        e2e_items.append(item)
        item.add_marker(pytest.mark.e2e)
        if not TEST_DATABASE_URL:
            item.add_marker(
                pytest.mark.skip(
                    reason="E2E omitido: define TEST_DATABASE_URL con una base PostgreSQL de pruebas."
                )
            )
    if TEST_DATABASE_URL:
        _validate_test_database_url(TEST_DATABASE_URL)
    items[:] = regular_items + e2e_items


@pytest.fixture(autouse=True)
def reset_rate_limit_window() -> None:
    # Limiter is process-global and keyed by constant ASGI client host.
    # Reset per test so suite volume does not decide outcomes.
    _rate_windows.clear()


def _alembic_config() -> Config:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    return config


def _reset_schema(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def e2e_database() -> AsyncGenerator[None, None]:
    if not TEST_DATABASE_URL:
        yield
        return

    _validate_test_database_url(TEST_DATABASE_URL)
    sync_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    _reset_schema(sync_engine)
    previous_database_url = settings.database_url
    previous_app_env = settings.app_env
    previous_ai_provider = settings.ai_provider
    from app.db import session as db_session

    previous_engine = db_session._engine
    if previous_engine is not None:
        await previous_engine.dispose()
    async_engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    async_factory = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    db_session._engine = async_engine
    db_session._session_factory = async_factory

    settings.database_url = TEST_DATABASE_URL
    settings.app_env = "test"
    settings.ai_provider = "demo"
    settings.validate_runtime_configuration()
    command.upgrade(_alembic_config(), "head")
    command.upgrade(_alembic_config(), "head")

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with app.router.lifespan_context(app):
            yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        await async_engine.dispose()
        _reset_schema(sync_engine)
        sync_engine.dispose()
        db_session._engine = None
        db_session._session_factory = None
        settings.database_url = previous_database_url
        settings.app_env = previous_app_env
        settings.ai_provider = previous_ai_provider


@pytest.fixture(scope="session")
def migrated_database() -> object:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL no está configurada.")
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest_asyncio.fixture
async def client_factory(
    e2e_database: None,
) -> AsyncGenerator[Callable[..., Awaitable[tuple[AsyncClient, str]]], None]:
    del e2e_database
    clients: list[AsyncClient] = []

    async def make_client(
        *, name: str = "E2E User", workspace_name: str = "E2E Workspace"
    ) -> tuple[AsyncClient, str]:
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        suffix = uuid.uuid4().hex
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"e2e-{suffix}@example.com",
                "name": name,
                "password": "e2e-password-segura-123",
                "workspace_name": f"{workspace_name} {suffix[:8]}",
            },
        )
        assert response.status_code == 201, response.text
        return client, response.json()["workspace"]["id"]

    try:
        yield make_client
    finally:
        for client in clients:
            await client.aclose()


@pytest_asyncio.fixture
async def authenticated_client(client_factory):
    client, workspace_id = await client_factory()
    return client, workspace_id


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> DeterministicE2EProvider:
    provider = DeterministicE2EProvider()
    monkeypatch.setattr("app.conversations.routes.get_content_provider", lambda **kwargs: provider)
    return provider


@pytest.fixture
def generation_payload() -> dict[str, str]:
    return {"text": "Crea una publicación E2E para mi producto"}


@pytest_asyncio.fixture
async def business_context(authenticated_client):
    client, workspace_id = authenticated_client
    business_response = await client.post(
        "/api/v1/businesses",
        json={
            "name": "Negocio E2E",
            "category": "gastronomy",
            "country": "Honduras",
            "city": "Tegucigalpa",
            "primary_product": "Café E2E",
            "target_audience": "Personas de la ciudad",
            "preferred_platforms": ["instagram", "tiktok"],
            "primary_objective": "sales",
        },
        headers={"X-Workspace-Id": workspace_id},
    )
    assert business_response.status_code == 201, business_response.text
    business = business_response.json()
    brand_response = await client.put(
        f"/api/v1/businesses/{business['id']}/brand-profile",
        json={
            "voice_tones": ["friendly"],
            "value_proposition": "Una propuesta E2E comprobable.",
            "preferred_words": ["artesanal"],
            "forbidden_words": ["barato"],
        },
        headers={"X-Workspace-Id": workspace_id},
    )
    assert brand_response.status_code == 200, brand_response.text
    conversation_response = await client.post(
        "/api/v1/conversations",
        json={"business_id": business["id"], "title": "Conversación E2E"},
        headers={"X-Workspace-Id": workspace_id},
    )
    assert conversation_response.status_code == 201, conversation_response.text
    return {
        "client": client,
        "workspace_id": workspace_id,
        "business": business,
        "conversation_id": conversation_response.json()["id"],
    }
