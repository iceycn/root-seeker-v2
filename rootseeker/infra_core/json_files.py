from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from rootseeker.infra_core.fs_safe import SafePathGuard

__all__ = ["AtomicJsonStore"]


class AtomicJsonStore:
    def __init__(self, workspace_root: Path) -> None:
        self._guard = SafePathGuard(workspace_root)

    def write(self, path: Path, payload: dict[str, Any]) -> None:
        safe_path = self._guard.ensure_safe(path)
        safe_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=safe_path.parent, delete=False) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            temp_path = Path(tmp.name)
        temp_path.replace(safe_path)

    def read(self, path: Path) -> dict[str, Any] | None:
        safe_path = self._guard.ensure_safe(path)
        if not safe_path.exists():
            return None
        return json.loads(safe_path.read_text(encoding="utf-8"))
