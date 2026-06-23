from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "ErrorChatHistoryStore",
    "FileErrorChatHistoryStore",
    "SqliteErrorChatHistoryStore",
    "build_error_history_store",
]


class ErrorChatHistoryStore(Protocol):
    def list_items(self) -> list[dict[str, Any]]:
        ...

    def append(self, item: dict[str, Any]) -> dict[str, Any]:
        ...

    def update(self, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        ...

    def clear(self) -> None:
        ...


class FileErrorChatHistoryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"items": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"items": []}
        data.setdefault("items", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_items(self) -> list[dict[str, Any]]:
        return list(self._load().get("items", []))

    def append(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item)
        payload.setdefault("id", str(uuid.uuid4()))
        payload.setdefault("created_at", datetime.now(UTC).isoformat())
        data = self._load()
        data.setdefault("items", []).append(payload)
        self._save(data)
        return payload

    def update(self, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        data = self._load()
        items = data.setdefault("items", [])
        for index, item in enumerate(items):
            if item.get("id") == item_id:
                updated = {**item, **patch}
                items[index] = updated
                self._save(data)
                return updated
        return None

    def clear(self) -> None:
        self._save({"items": []})


class SqliteErrorChatHistoryStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS error_chat_history (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def list_items(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM error_chat_history ORDER BY created_at ASC"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def append(self, item: dict[str, Any]) -> dict[str, Any]:
        payload = dict(item)
        payload.setdefault("id", str(uuid.uuid4()))
        payload.setdefault("created_at", datetime.now(UTC).isoformat())
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO error_chat_history (id, created_at, payload) VALUES (?, ?, ?)",
                (payload["id"], payload["created_at"], json.dumps(payload, ensure_ascii=False)),
            )
        return payload

    def update(self, item_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM error_chat_history WHERE id = ?",
                (item_id,),
            ).fetchone()
            if row is None:
                return None
            payload = {**json.loads(row[0]), **patch}
            conn.execute(
                "UPDATE error_chat_history SET payload = ? WHERE id = ?",
                (json.dumps(payload, ensure_ascii=False), item_id),
            )
        return payload

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM error_chat_history")


def build_error_history_store(repo_root: Path) -> ErrorChatHistoryStore:
    import os

    (repo_root / "data" / "admin").mkdir(parents=True, exist_ok=True)
    store_kind = (os.getenv("ROOTSEEKER_ERROR_HISTORY_STORE") or "file").strip().lower()
    if store_kind == "sqlite":
        path = os.getenv("ROOTSEEKER_ERROR_HISTORY_SQLITE_PATH") or str(
            repo_root / "data" / "admin" / "error_history.db"
        )
        return SqliteErrorChatHistoryStore(path)
    path = os.getenv("ROOTSEEKER_ERROR_HISTORY_FILE") or str(
        repo_root / "data" / "admin" / "error_history.json"
    )
    return FileErrorChatHistoryStore(path)
