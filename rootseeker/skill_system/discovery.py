from __future__ import annotations

from pathlib import Path

__all__ = ["discover_skill_files", "SKILL_FILENAME"]

SKILL_FILENAME = "SKILL.md"


def discover_skill_files(builtin_skills_root: Path) -> list[Path]:
    if not builtin_skills_root.is_dir():
        return []
    return sorted(builtin_skills_root.rglob(SKILL_FILENAME))
