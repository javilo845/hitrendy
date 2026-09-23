#!/usr/bin/env python3
"""Restore drill for a disposable beta verification database.

The target must end in ``_restore`` unless the operator explicitly confirms
``RESTORE``. This prevents an accidental command from replacing a live beta
database.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

try:
    from scripts.backup import _database_kind, _safe_postgres_url, _sha256, _sqlite_path
except ModuleNotFoundError:  # Running the file directly from the scripts folder.
    from backup import _database_kind, _safe_postgres_url, _sha256, _sqlite_path


def restore_backup(
    *,
    backup_path: Path,
    target_database_url: str,
    confirmation: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    dry_run: bool = False,
) -> Path:
    if not backup_path.exists():
        raise FileNotFoundError(backup_path)
    _verify_manifest(backup_path)
    kind = _database_kind(target_database_url)
    if dry_run:
        return backup_path
    if confirmation != "RESTORE" and not _target_is_restore_database(target_database_url, kind):
        raise ValueError("El destino debe terminar en _restore o requerir confirmación RESTORE.")

    if kind == "sqlite":
        target = _sqlite_path(target_database_url)
        if target.resolve() == backup_path.resolve():
            raise ValueError("El destino SQLite no puede ser el propio backup.")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, target)
        return target

    safe_url, password = _safe_postgres_url(target_database_url)
    environment = os.environ.copy()
    if password is not None:
        environment["PGPASSWORD"] = password
    runner(
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--dbname",
            safe_url,
            str(backup_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    return backup_path


def _verify_manifest(backup_path: Path) -> None:
    manifest_path = backup_path.with_suffix(backup_path.suffix + ".manifest.json")
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("El manifiesto del backup no se puede leer.") from exc
    expected = manifest.get("sha256") if isinstance(manifest, dict) else None
    if not isinstance(expected, str) or not hmac.compare_digest(_sha256(backup_path), expected):
        raise ValueError("La suma SHA-256 del backup no coincide con su manifiesto.")


def _target_is_restore_database(database_url: str, kind: str) -> bool:
    if kind == "sqlite":
        return _sqlite_path(database_url).stem.endswith("_restore")
    database_name = unquote(urlparse(database_url).path.lstrip("/")).split("?", 1)[0]
    return database_name.endswith("_restore")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore drill controlado de HiTrendy")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--target-database-url", required=True)
    parser.add_argument("--confirm", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = restore_backup(
        backup_path=args.backup,
        target_database_url=args.target_database_url,
        confirmation=args.confirm,
        dry_run=args.dry_run,
    )
    print(result)


if __name__ == "__main__":
    main()
