from __future__ import annotations

from pathlib import Path

__all__ = ["discover_skill_files", "SKILL_FILENAME"]

SKILL_FILENAME = "SKILL.md"


def discover_skill_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob(SKILL_FILENAME))
