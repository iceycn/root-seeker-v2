"""Message notification template store (file / sqlite / mysql)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from rootseeker.channel_routing.notify_variables import SYSTEM_DEFAULT_TEMPLATE_BODY, SYSTEM_TEMPLATE_ID
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.backend_resolve import resolve_message_template_store
from rootseeker.storage.mysql_conn import MysqlConnectConfig, mysql_config_from_settings, mysql_connection

__all__ = [
    "FileMessageTemplateStore",
    "MessageTemplateStore",
    "MysqlMessageTemplateStore",
    "SYSTEM_TEMPLATE_ID",
    "SqliteMessageTemplateStore",
    "build_message_template_store",
]


class MessageTemplateStore(Protocol):
    def list_templates(self) -> list[dict[str, Any]]: ...

    def get_template(self, template_id: str) -> dict[str, Any] | None: ...

    def upsert_template(self, template: dict[str, Any]) -> dict[str, Any]: ...

    def delete_template(self, template_id: str) -> None: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _system_template_payload() -> dict[str, Any]:
    now = _now_iso()
    return {
        "template_id": SYSTEM_TEMPLATE_ID,
        "name": "默认通知",
        "kind": "system",
        "body": SYSTEM_DEFAULT_TEMPLATE_BODY,
        "description": "系统内置默认通知模板",
        "created_at": now,
        "updated_at": now,
    }


def _sort_templates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[int, str]:
        kind_rank = 0 if item.get("kind") == "system" else 1
        return (kind_rank, str(item.get("name") or ""))

    return sorted(items, key=key)


def _normalize_template_payload(
    template: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(template.get("name") or (existing or {}).get("name") or "").strip()
    if not name:
        raise ValueError("name is required")

    body = str(template.get("body") if "body" in template else (existing or {}).get("body") or "").strip()
    if not body:
        raise ValueError("body is required")

    template_id = str(
        template.get("template_id") or (existing or {}).get("template_id") or uuid.uuid4()
    ).strip()
    if not template_id:
        template_id = str(uuid.uuid4())

    if template_id == SYSTEM_TEMPLATE_ID or (existing or {}).get("kind") == "system":
        kind = "system"
        template_id = SYSTEM_TEMPLATE_ID
    else:
        kind = "custom"
        requested_kind = str(template.get("kind") or "").strip().lower()
        if requested_kind == "system":
            raise ValueError("cannot create additional system templates")

    description = str(
        template.get("description")
        if "description" in template
        else (existing or {}).get("description")
        or ""
    )
    now = _now_iso()
    created_at = str((existing or {}).get("created_at") or template.get("created_at") or now)
    return {
        "template_id": template_id,
        "name": name,
        "kind": kind,
        "body": body,
        "description": description,
        "created_at": created_at,
        "updated_at": now,
    }


class FileMessageTemplateStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"templates": [_system_template_payload()]})
        else:
            self.ensure_system_template()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"templates": [_system_template_payload()]}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"templates": [_system_template_payload()]}
        data.setdefault("templates", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def ensure_system_template(self) -> None:
        data = self._load()
        templates = [item for item in data.get("templates", []) if isinstance(item, dict)]
        if any(item.get("template_id") == SYSTEM_TEMPLATE_ID for item in templates):
            return
        templates.insert(0, _system_template_payload())
        data["templates"] = templates
        self._save(data)

    def list_templates(self) -> list[dict[str, Any]]:
        self.ensure_system_template()
        items = [item for item in self._load().get("templates", []) if isinstance(item, dict)]
        return _sort_templates(items)

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        tid = str(template_id or "").strip()
        for item in self.list_templates():
            if item.get("template_id") == tid:
                return dict(item)
        return None

    def upsert_template(self, template: dict[str, Any]) -> dict[str, Any]:
        self.ensure_system_template()
        data = self._load()
        templates = [item for item in data.get("templates", []) if isinstance(item, dict)]
        template_id = str(template.get("template_id") or "").strip()
        existing = next((item for item in templates if item.get("template_id") == template_id), None)
        if existing is None:
            name = str(template.get("name") or "").strip()
            existing = next((item for item in templates if item.get("name") == name), None)
        normalized = _normalize_template_payload(template, existing=existing)
        templates = [item for item in templates if item.get("template_id") != normalized["template_id"]]
        templates.append(normalized)
        data["templates"] = templates
        self._save(data)
        return normalized

    def delete_template(self, template_id: str) -> None:
        tid = str(template_id or "").strip()
        if tid == SYSTEM_TEMPLATE_ID:
            raise ValueError("cannot delete system template")
        existing = self.get_template(tid)
        if existing and existing.get("kind") == "system":
            raise ValueError("cannot delete system template")
        data = self._load()
        templates = [
            item
            for item in data.get("templates", [])
            if isinstance(item, dict) and item.get("template_id") != tid
        ]
        data["templates"] = templates
        self._save(data)
        self.ensure_system_template()


class SqliteMessageTemplateStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()
        self.ensure_system_template()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    body TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _row_to_template(self, row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "template_id": row[0],
            "name": row[1],
            "kind": row[2],
            "body": row[3],
            "description": row[4] or "",
            "created_at": row[5],
            "updated_at": row[6],
        }

    def ensure_system_template(self) -> None:
        if self.get_template(SYSTEM_TEMPLATE_ID) is not None:
            return
        payload = _system_template_payload()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO message_templates (
                    template_id, name, kind, body, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["template_id"],
                    payload["name"],
                    payload["kind"],
                    payload["body"],
                    payload["description"],
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )

    def list_templates(self) -> list[dict[str, Any]]:
        self.ensure_system_template()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT template_id, name, kind, body, description, created_at, updated_at
                FROM message_templates
                """
            ).fetchall()
        return _sort_templates([self._row_to_template(row) for row in rows])

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT template_id, name, kind, body, description, created_at, updated_at
                FROM message_templates WHERE template_id = ?
                """,
                (str(template_id or "").strip(),),
            ).fetchone()
        return self._row_to_template(row) if row else None

    def upsert_template(self, template: dict[str, Any]) -> dict[str, Any]:
        self.ensure_system_template()
        template_id = str(template.get("template_id") or "").strip()
        existing = self.get_template(template_id) if template_id else None
        if existing is None:
            name = str(template.get("name") or "").strip()
            existing = next((item for item in self.list_templates() if item.get("name") == name), None)
        normalized = _normalize_template_payload(template, existing=existing)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO message_templates (
                    template_id, name, kind, body, description, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["template_id"],
                    normalized["name"],
                    normalized["kind"],
                    normalized["body"],
                    normalized["description"],
                    normalized["created_at"],
                    normalized["updated_at"],
                ),
            )
        return normalized

    def delete_template(self, template_id: str) -> None:
        tid = str(template_id or "").strip()
        if tid == SYSTEM_TEMPLATE_ID:
            raise ValueError("cannot delete system template")
        existing = self.get_template(tid)
        if existing and existing.get("kind") == "system":
            raise ValueError("cannot delete system template")
        with self._connect() as conn:
            conn.execute("DELETE FROM message_templates WHERE template_id = ?", (tid,))
        self.ensure_system_template()


class MysqlMessageTemplateStore:
    def __init__(self, config: MysqlConnectConfig) -> None:
        self.config = config
        self._init()
        self.ensure_system_template()

    def _connect(self):
        return mysql_connection(self.config)

    def _init(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS message_templates (
                        template_id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        kind VARCHAR(32) NOT NULL,
                        body TEXT NOT NULL,
                        description TEXT,
                        created_at VARCHAR(64) NOT NULL,
                        updated_at VARCHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def _row_to_template(self, row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "template_id": row[0],
            "name": row[1],
            "kind": row[2],
            "body": row[3],
            "description": row[4] or "",
            "created_at": row[5],
            "updated_at": row[6],
        }

    def ensure_system_template(self) -> None:
        if self.get_template(SYSTEM_TEMPLATE_ID) is not None:
            return
        payload = _system_template_payload()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO message_templates (
                        template_id, name, kind, body, description, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        payload["template_id"],
                        payload["name"],
                        payload["kind"],
                        payload["body"],
                        payload["description"],
                        payload["created_at"],
                        payload["updated_at"],
                    ),
                )

    def list_templates(self) -> list[dict[str, Any]]:
        self.ensure_system_template()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT template_id, name, kind, body, description, created_at, updated_at
                    FROM message_templates
                    """
                )
                rows = cur.fetchall()
        return _sort_templates([self._row_to_template(row) for row in rows])

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT template_id, name, kind, body, description, created_at, updated_at
                    FROM message_templates WHERE template_id = %s
                    """,
                    (str(template_id or "").strip(),),
                )
                row = cur.fetchone()
        return self._row_to_template(row) if row else None

    def upsert_template(self, template: dict[str, Any]) -> dict[str, Any]:
        self.ensure_system_template()
        template_id = str(template.get("template_id") or "").strip()
        existing = self.get_template(template_id) if template_id else None
        if existing is None:
            name = str(template.get("name") or "").strip()
            existing = next((item for item in self.list_templates() if item.get("name") == name), None)
        normalized = _normalize_template_payload(template, existing=existing)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO message_templates (
                        template_id, name, kind, body, description, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        kind = VALUES(kind),
                        body = VALUES(body),
                        description = VALUES(description),
                        updated_at = VALUES(updated_at)
                    """,
                    (
                        normalized["template_id"],
                        normalized["name"],
                        normalized["kind"],
                        normalized["body"],
                        normalized["description"],
                        normalized["created_at"],
                        normalized["updated_at"],
                    ),
                )
        return normalized

    def delete_template(self, template_id: str) -> None:
        tid = str(template_id or "").strip()
        if tid == SYSTEM_TEMPLATE_ID:
            raise ValueError("cannot delete system template")
        existing = self.get_template(tid)
        if existing and existing.get("kind") == "system":
            raise ValueError("cannot delete system template")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM message_templates WHERE template_id = %s", (tid,))
        self.ensure_system_template()


def build_message_template_store(
    repo_root: Path,
    *,
    settings: RootSeekerSettings | None = None,
) -> MessageTemplateStore:
    cfg = settings or RootSeekerSettings()
    (repo_root / "data" / "admin").mkdir(parents=True, exist_ok=True)
    store_kind = resolve_message_template_store(cfg)
    if store_kind == "mysql":
        return MysqlMessageTemplateStore(mysql_config_from_settings(cfg))
    if store_kind == "sqlite":
        path = Path(cfg.message_template_sqlite_path)
        if not path.is_absolute():
            path = repo_root / path
        return SqliteMessageTemplateStore(path)
    path = Path(cfg.message_template_file)
    if not path.is_absolute():
        path = repo_root / path
    return FileMessageTemplateStore(path)
