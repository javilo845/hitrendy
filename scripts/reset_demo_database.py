#!/usr/bin/env python3
"""Reset the local HiTrendy demo database and its local uploaded assets safely."""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "starter" / "backend"
DEMO_DATABASE = ROOT / "hitrendy_demo.db"
DEMO_STORAGE = ROOT / "storage"


def demo_database_url(database: Path = DEMO_DATABASE) -> str:
    return f"sqlite:///{database.resolve()}"


def assert_safe_demo_target(database: Path, root: Path = ROOT) -> None:
    resolved_root = root.resolve()
    resolved_database = database.resolve()
    if database.name != "hitrendy_demo.db" or not resolved_database.is_relative_to(
        resolved_root
    ):
        raise ValueError(
            "El reinicio solo permite la base local hitrendy_demo.db del repositorio."
        )


def remove_demo_data(database: Path, storage: Path) -> None:
    for candidate in (
        database,
        database.with_name(f"{database.name}-wal"),
        database.with_name(f"{database.name}-shm"),
    ):
        if candidate.exists():
            candidate.unlink()
    if storage.exists():
        shutil.rmtree(storage)


async def seed_templates() -> None:
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.db.session import get_session_factory
    from app.templates.repository import seed_templates as seed

    async with get_session_factory() as session:
        await seed(session)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recrea la base y el almacenamiento locales de la demo de HiTrendy."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirma que se eliminarán hitrendy_demo.db y storage/ locales.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm:
        print(
            "Rechazado: ejecuta con --confirm para reiniciar los datos locales de demo."
        )
        return 2
    if os.environ.get("APP_ENV") == "production":
        print("Rechazado: el reinicio de demo no puede ejecutarse en producción.")
        return 2

    assert_safe_demo_target(DEMO_DATABASE)
    os.environ["APP_ENV"] = "development"
    os.environ["AI_PROVIDER"] = "demo"
    os.environ["VISION_PROVIDER"] = "demo"
    os.environ["DATABASE_URL"] = demo_database_url()
    remove_demo_data(DEMO_DATABASE, DEMO_STORAGE)

    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=os.environ.copy(),
        check=True,
    )
    asyncio.run(seed_templates())
    print("Demo reiniciada: esquema migrado y catálogo de plantillas sembrado.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(f"No pudimos reiniciar la demo: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
