from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class SetupState:
    """Persisted setup progress for resume."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = data or {"version": 1, "steps": {}}
        self._data.setdefault("version", 1)
        self._data.setdefault("steps", {})

    @classmethod
    def load(cls, path: Path) -> SetupState:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return cls()
        return cls(raw)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        fd, tmp_name = tempfile.mkstemp(prefix=".setup-state-", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.write("\n")
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def mark_done(self, step: str, meta: dict[str, Any] | None = None) -> None:
        steps = self._data.setdefault("steps", {})
        steps[step] = {"done": True, "meta": dict(meta or {})}

    def is_done(self, step: str) -> bool:
        entry = self._data.get("steps", {}).get(step)
        return bool(isinstance(entry, dict) and entry.get("done"))

    def meta(self, step: str) -> dict[str, Any]:
        entry = self._data.get("steps", {}).get(step)
        if not isinstance(entry, dict):
            return {}
        meta = entry.get("meta")
        return dict(meta) if isinstance(meta, dict) else {}

    def set_meta(self, step: str, meta: dict[str, Any]) -> None:
        steps = self._data.setdefault("steps", {})
        entry = steps.get(step)
        if not isinstance(entry, dict):
            entry = {"done": False, "meta": {}}
            steps[step] = entry
        entry["meta"] = dict(meta)
