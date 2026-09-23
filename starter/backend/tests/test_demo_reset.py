from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_reset_module():
    script = Path(__file__).resolve().parents[3] / "scripts" / "reset_demo_database.py"
    spec = importlib.util.spec_from_file_location("reset_demo_database", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_reset_rejects_non_demo_or_external_database(tmp_path: Path) -> None:
    reset = _load_reset_module()

    reset.assert_safe_demo_target(tmp_path / "hitrendy_demo.db", tmp_path)
    with pytest.raises(ValueError):
        reset.assert_safe_demo_target(tmp_path / "hitrendy.db", tmp_path)
    with pytest.raises(ValueError):
        reset.assert_safe_demo_target(Path("/tmp/hitrendy_demo.db"), tmp_path)
