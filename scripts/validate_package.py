from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "docs" / "INDEX.md",
    ROOT / "project-manifest.yaml",
    ROOT / "design" / "tokens.css",
    ROOT / "contracts" / "schemas" / "generated-social-post.schema.json",
    ROOT / "demo" / "app.py",
]


def main() -> None:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED if not path.exists()]
    if missing:
        raise SystemExit(f"Missing required files: {missing}")

    json_files = []
    for path in ROOT.rglob("*.json"):
        if any(part in path.parts for part in ["node_modules", ".venv", ".env"]):
            continue
        json_files.append(path)

    for path in json_files:
        with path.open(encoding="utf-8") as file:
            try:
                json.load(file)
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON in file {path}: {e}")
                raise e

    docs = list((ROOT / "docs").rglob("*.md"))
    docs_without_id = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        if path.name != "INDEX.md" and not text.startswith("---\n"):
            docs_without_id.append(str(path.relative_to(ROOT)))
    if docs_without_id:
        raise SystemExit(f"Documentation missing frontmatter: {docs_without_id}")

    print(f"Package valid: {len(json_files)} JSON files, {len(docs)} documentation files.")


if __name__ == "__main__":
    main()
