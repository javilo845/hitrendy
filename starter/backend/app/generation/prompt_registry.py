from __future__ import annotations

from functools import lru_cache
from pathlib import Path

PROMPT_ROOT = Path(__file__).resolve().parents[4] / "contracts" / "prompts"


def _load_prompt(filename: str, prompt_id: str) -> tuple[str, str]:
    prompt = (PROMPT_ROOT / filename).read_text(encoding="utf-8")
    version = "1.0.0"
    for line in prompt.splitlines():
        if line.startswith("version:"):
            version = line.split(":", 1)[1].strip()
            break
    return prompt, f"{prompt_id}@{version}"


@lru_cache(maxsize=8)
def get_social_copy_prompt() -> tuple[str, str]:
    return _load_prompt("social-copy.system.md", "social-copy")


@lru_cache(maxsize=8)
def get_short_video_script_prompt() -> tuple[str, str]:
    return _load_prompt("short-video-script.system.md", "short-video-script")
