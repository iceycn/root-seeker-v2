from __future__ import annotations

from pathlib import Path

__all__ = ["SafePathGuard"]


class SafePathGuard:
    def __init__(self, workspace_root: Path) -> None:
        self._root = workspace_root.resolve()

    def ensure_safe(self, target: Path) -> Path:
        resolved = target.resolve()
        try:
            resolved.relative_to(self._root)
        except ValueError as exc:
            raise ValueError(f"path escapes workspace root: {target}") from exc
        return resolved
