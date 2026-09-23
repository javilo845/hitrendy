#!/usr/bin/env python3
"""Create a beta database backup and a non-sensitive verification manifest.

PostgreSQL backups use ``pg_dump`` once, as a release/cron operation. SQLite is
supported only for local restore drills. The command never prints a database
URL or a secret.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse


def _database_kind(database_url: str) -> str:
    scheme = urlparse(database_url).scheme
    if scheme.startswith("sqlite"):
        return "sqlite"
    if scheme in {"postgresql", "postgresql+psycopg"}:
        return "postgresql"
    raise ValueError("DATABASE_URL debe usar SQLite o PostgreSQL.")


def _sqlite_path(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("La URL SQLite del backup no debe incluir query ni fragmento.")
    raw = unquote(parsed.path)
    if not raw:
        raise ValueError("La URL SQLite del backup debe incluir una ruta.")
    # SQLite uses three slashes for a path relative to the process directory
    # and four for an absolute filesystem path. ``urlparse`` leaves the
    # leading slash in both forms, so distinguish ``/relative`` from
    # ``//absolute`` explicitly.
    path = Path(raw[1:] if raw.startswith("//") else raw.lstrip("/"))
    return path.resolve()


def _safe_postgres_url(database_url: str) -> tuple[str, str | None]:
    parsed = urlparse(database_url)
    password = unquote(parsed.password) if parsed.password else None
    hostname = parsed.hostname or ""
    user = unquote(parsed.username) if parsed.username else ""
    auth = f"{user}@" if user else ""
    host = hostname
    if ":" in hostname and not hostname.startswith("["):
        host = f"[{hostname}]"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    safe_netloc = f"{auth}{host}"
    safe = parsed._replace(netloc=safe_netloc).geturl()
    return safe, password


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(
    *,
    database_url: str,
    output_dir: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    dry_run: bool = False,
) -> Path:
    kind = _database_kind(database_url)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact = output_dir / f"hitrendy-{stamp}.{'sqlite' if kind == 'sqlite' else 'dump'}"
    if dry_run:
        return artifact

    if kind == "sqlite":
        source = _sqlite_path(database_url)
        if not source.exists():
            raise FileNotFoundError(source)
        shutil.copy2(source, artifact)
    else:
        safe_url, password = _safe_postgres_url(database_url)
        environment = os.environ.copy()
        if password is not None:
            environment["PGPASSWORD"] = password
        runner(
            ["pg_dump", "--format=custom", "--no-owner", "--file", str(artifact), safe_url],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )

    manifest = {
        "format": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "filename": artifact.name,
        "sha256": _sha256(artifact),
        "retention_days": int(os.environ.get("DATA_RETENTION_DAYS", "365")),
    }
    (artifact.with_suffix(artifact.suffix + ".manifest.json")).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Backup controlado de HiTrendy")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    parser.add_argument("--output-dir", type=Path, default=Path("backups"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL es obligatorio")
    artifact = create_backup(
        database_url=args.database_url,
        output_dir=args.output_dir,
        dry_run=args.dry_run,
    )
    print(artifact)


if __name__ == "__main__":
    main()
