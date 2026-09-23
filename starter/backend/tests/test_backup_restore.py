from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.backup import _sqlite_path, create_backup  # noqa: E402
from scripts.restore_drill import restore_backup  # noqa: E402


def test_sqlite_backup_and_restore_drill(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"demo database")
    backup = create_backup(
        database_url=f"sqlite:///{source}",
        output_dir=tmp_path / "backups",
    )
    target = tmp_path / "beta_restore.db"
    restored = restore_backup(
        backup_path=backup,
        target_database_url=f"sqlite:///{target}",
        confirmation="",
    )
    assert restored == target
    assert target.read_bytes() == source.read_bytes()
    assert backup.with_suffix(backup.suffix + ".manifest.json").exists()


def test_relative_sqlite_url_resolves_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert _sqlite_path("sqlite:///./hitrendy.db") == (tmp_path / "hitrendy.db").resolve()


def test_restore_dry_run_does_not_touch_another_database(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"demo database")
    backup = create_backup(database_url=f"sqlite:///{source}", output_dir=tmp_path / "backups")
    target = tmp_path / "ordinary.db"
    target.write_bytes(b"keep me")
    restore_backup(
        backup_path=backup,
        target_database_url=f"sqlite:///{target}",
        confirmation="",
        dry_run=True,
    )
    assert target.read_bytes() == b"keep me"


def test_postgres_backup_and_restore_never_put_password_in_argv(tmp_path: Path) -> None:
    backup_calls: list[tuple[list[str], dict[str, object]]] = []

    def backup_runner(command: list[str], **kwargs):
        backup_calls.append((command, kwargs))
        Path(command[4]).write_bytes(b"custom-format-backup")
        return subprocess.CompletedProcess(command, 0)

    backup = create_backup(
        database_url="postgresql+psycopg://backup_user:secret@db.example/hitrendy_test",
        output_dir=tmp_path / "backups",
        runner=backup_runner,
    )
    command, kwargs = backup_calls[0]
    assert "secret" not in " ".join(command)
    assert kwargs["env"]["PGPASSWORD"] == "secret"

    restore_calls: list[tuple[list[str], dict[str, object]]] = []

    def restore_runner(command: list[str], **kwargs):
        restore_calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    restore_backup(
        backup_path=backup,
        target_database_url="postgresql+psycopg://backup_user:secret@db.example/hitrendy_test_restore",
        confirmation="",
        runner=restore_runner,
    )
    restore_command, restore_kwargs = restore_calls[0]
    assert "secret" not in " ".join(restore_command)
    assert restore_kwargs["env"]["PGPASSWORD"] == "secret"


def test_restore_rejects_a_corrupted_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"demo database")
    backup = create_backup(database_url=f"sqlite:///{source}", output_dir=tmp_path / "backups")
    backup.write_bytes(b"tampered")

    with pytest.raises(ValueError, match="SHA-256"):
        restore_backup(
            backup_path=backup,
            target_database_url=f"sqlite:///{tmp_path / 'beta_restore.db'}",
            confirmation="",
            dry_run=True,
        )
