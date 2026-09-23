from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.assets.models  # noqa: F401
import app.business.models  # noqa: F401
import app.conversations.models  # noqa: F401
import app.images.models  # noqa: F401
import app.projects.models  # noqa: F401
import app.social.models  # noqa: F401
import app.templates.models  # noqa: F401
import app.trends.models  # noqa: F401
from app.conversations.models import AIUsageEvent
from app.db.base import Base
from app.dependencies import get_db
from app.identity.models import (
    AccountPurgeJob,
    AdminAuditEvent,
    AuthSession,
    OAuthAccount,
    OAuthAuthorizationRequest,
    PendingSignup,
    User,
    UserPreference,
    Workspace,
    WorkspaceMember,
)
from app.main import app
from app.operations.models import (
    AbuseReport,
    BetaInvite,
    PasswordResetToken,
    ProductFeedback,
    UsageAdjustment,
)
from app.social.models import SocialConnection
from app.templates.repository import seed_templates

TEST_DB_URL = "sqlite+aiosqlite:///./test_hitrendy_secure.db"

_async_engine = create_async_engine(TEST_DB_URL, echo=False)
_TestingSessionFactory = async_sessionmaker(
    _async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

_sync_engine = create_engine("sqlite:///./test_hitrendy_secure.db")


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=_sync_engine)
    yield
    Base.metadata.drop_all(bind=_sync_engine)
    _sync_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def apply_test_defaults():
    import app.core.config as config_module

    config_module.settings.app_env = "test"
    config_module.settings.csrf_enabled = False


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _TestingSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        token = "test-session-token"
        async with _TestingSessionFactory() as session:
            for model in (
                AbuseReport,
                ProductFeedback,
                UsageAdjustment,
                AIUsageEvent,
                PasswordResetToken,
                AccountPurgeJob,
                BetaInvite,
                SocialConnection,
                AdminAuditEvent,
                AuthSession,
                OAuthAuthorizationRequest,
                OAuthAccount,
                PendingSignup,
                WorkspaceMember,
                UserPreference,
                User,
                Workspace,
            ):
                await session.execute(delete(model))
            user = User(
                id="usr_test_001",
                email="test@example.com",
                name="Test User",
                password_hash="scrypt$00$00",
            )
            workspace = Workspace(id="ws_test_001", name="Test workspace")
            membership = WorkspaceMember(
                id="wsm_test_001", workspace_id=workspace.id, user_id=user.id, role="owner"
            )
            auth_session = AuthSession(
                id="ses_test_001",
                token_hash=sha256(token.encode("utf-8")).hexdigest(),
                user_id=user.id,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add_all([user, workspace, membership, auth_session])
            await session.commit()
        ac.cookies.set("hitrendy_session", token)
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session(client: AsyncClient) -> AsyncGenerator[AsyncSession, None]:
    async with _TestingSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_client(client: AsyncClient) -> AsyncClient:
    async for session in app.dependency_overrides[get_db]():
        await seed_templates(session)
    return client
