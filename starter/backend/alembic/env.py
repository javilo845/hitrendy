from __future__ import annotations

from logging.config import fileConfig
from os import environ
from urllib.parse import unquote, urlparse

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.assets import models as asset_models  # noqa: F401
from app.business import models as business_models  # noqa: F401
from app.conversations import models as conversation_models  # noqa: F401
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_database_engine_options
from app.identity import models as identity_models  # noqa: F401
from app.images import models as image_models  # noqa: F401
from app.operations import models as operations_models  # noqa: F401
from app.projects import models as project_models  # noqa: F401
from app.social import models as social_models  # noqa: F401
from app.templates import models as template_models  # noqa: F401
from app.trends import models as trend_models  # noqa: F401
from app.videos import models as video_models  # noqa: F401

config = context.config


def _migration_database_url() -> str:
    test_url = environ.get("TEST_DATABASE_URL", "").strip()
    if not test_url:
        return settings.database_url
    parsed = urlparse(test_url)
    database_name = unquote(parsed.path.lstrip("/")).split("?", 1)[0]
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"} or not database_name.endswith(
        ("_test", "_e2e")
    ):
        raise RuntimeError(
            "TEST_DATABASE_URL sólo puede apuntar a una base PostgreSQL cuyo nombre "
            "termine en _test o _e2e."
        )
    return test_url


config.set_main_option("sqlalchemy.url", _migration_database_url().replace("+aiosqlite", ""))
if config.config_file_name is not None:
    # Alembic is also invoked in-process by migration tests.  Preserve the
    # application's HTTP logger instead of silently disabling it afterwards.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine_options = get_database_engine_options()
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=engine_options.get("connect_args", {}),
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
