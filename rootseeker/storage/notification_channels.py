"""Notification channel configuration store (file / sqlite / mysql)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.backend_resolve import resolve_notification_channel_store
from rootseeker.storage.mysql_conn import MysqlConnectConfig, mysql_config_from_settings, mysql_connection

__all__ = [
    "ALLOWED_CHANNEL_TYPES",
    "FileNotificationChannelStore",
    "MysqlNotificationChannelStore",
    "NotificationChannelStore",
    "SqliteNotificationChannelStore",
    "build_notification_channel_store",
    "mask_channel_for_api",
    "migrate_legacy_callbacks_from_admin",
]

ALLOWED_CHANNEL_TYPES = frozenset(
    {"webhook", "feishu", "dingtalk", "wechat_work", "slack", "discord"}
)

_DEFAULT_SETTINGS: dict[str, Any] = {"broadcast_enabled": True}


class NotificationChannelStore(Protocol):
    def list_channels(self) -> list[dict[str, Any]]: ...

    def get_channel(self, channel_id: str) -> dict[str, Any] | None: ...

    def upsert_channel(self, channel: dict[str, Any]) -> dict[str, Any]: ...

    def delete_channel(self, channel_id: str) -> None: ...

    def get_settings(self) -> dict[str, Any]: ...

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validate_channel_type(channel_type: str) -> str:
    normalized = str(channel_type or "").strip().lower()
    if normalized not in ALLOWED_CHANNEL_TYPES:
        raise ValueError(f"unsupported channel_type: {channel_type}")
    return normalized


def mask_channel_for_api(channel: dict[str, Any]) -> dict[str, Any]:
    payload = dict(channel)
    secret = str(payload.get("secret") or "")
    payload["has_secret"] = bool(secret)
    payload["masked_secret"] = "******" if secret else ""
    payload.pop("secret", None)
    return payload


def _sort_channels(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (int(item.get("sort_order") or 0), str(item.get("name") or "")),
    )


def _normalize_channel_payload(
    channel: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(channel.get("name") or (existing or {}).get("name") or "").strip()
    if not name:
        raise ValueError("name is required")

    channel_id = str(channel.get("channel_id") or (existing or {}).get("channel_id") or uuid.uuid4())
    channel_type = _validate_channel_type(
        str(channel.get("channel_type") or (existing or {}).get("channel_type") or "webhook")
    )
    endpoint_url = str(
        channel.get("endpoint_url") if "endpoint_url" in channel else (existing or {}).get("endpoint_url") or ""
    ).strip()
    if not endpoint_url:
        raise ValueError("endpoint_url is required")

    secret_raw = channel.get("secret") if "secret" in channel else None
    if secret_raw is None and existing is not None:
        secret = str(existing.get("secret") or "")
    else:
        secret = str(secret_raw or "")

    now = _now_iso()
    created_at = str((existing or {}).get("created_at") or channel.get("created_at") or now)
    metadata = channel.get("metadata") if "metadata" in channel else (existing or {}).get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    enabled = channel.get("enabled") if "enabled" in channel else (existing or {}).get("enabled", True)
    sort_order = channel.get("sort_order") if "sort_order" in channel else (existing or {}).get("sort_order", 0)

    return {
        "channel_id": channel_id,
        "name": name,
        "channel_type": channel_type,
        "endpoint_url": endpoint_url,
        "secret": secret,
        "enabled": bool(enabled),
        "sort_order": int(sort_order or 0),
        "metadata": dict(metadata),
        "created_at": created_at,
        "updated_at": now,
    }


class FileNotificationChannelStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"channels": [], "settings": dict(_DEFAULT_SETTINGS)})

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"channels": [], "settings": dict(_DEFAULT_SETTINGS)}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"channels": [], "settings": dict(_DEFAULT_SETTINGS)}
        data.setdefault("channels", [])
        data.setdefault("settings", dict(_DEFAULT_SETTINGS))
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_channels(self) -> list[dict[str, Any]]:
        return _sort_channels(list(self._load().get("channels", [])))

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        for item in self.list_channels():
            if item.get("channel_id") == channel_id:
                return dict(item)
        return None

    def upsert_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        items = list(data.get("channels", []))
        channel_id = str(channel.get("channel_id") or "").strip()
        existing = next((item for item in items if item.get("channel_id") == channel_id), None) if channel_id else None
        if existing is None:
            name = str(channel.get("name") or "").strip()
            existing = next((item for item in items if item.get("name") == name), None)
        normalized = _normalize_channel_payload(channel, existing=existing)
        for other in items:
            if other.get("name") == normalized["name"] and other.get("channel_id") != normalized["channel_id"]:
                raise ValueError(f"channel name already exists: {normalized['name']}")
        items = [item for item in items if item.get("channel_id") != normalized["channel_id"]]
        items.append(normalized)
        data["channels"] = items
        self._save(data)
        return dict(normalized)

    def delete_channel(self, channel_id: str) -> None:
        data = self._load()
        data["channels"] = [
            item for item in data.get("channels", []) if item.get("channel_id") != channel_id
        ]
        self._save(data)

    def get_settings(self) -> dict[str, Any]:
        settings = dict(self._load().get("settings", {}))
        settings.setdefault("broadcast_enabled", True)
        return settings

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        settings = dict(data.get("settings", {}))
        settings.update(dict(patch))
        data["settings"] = settings
        self._save(data)
        return settings


class SqliteNotificationChannelStore:
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
                CREATE TABLE IF NOT EXISTS notification_channels (
                    channel_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    channel_type TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    secret TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_channel_settings (
                    settings_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            row = conn.execute(
                "SELECT payload FROM notification_channel_settings WHERE settings_key = ?",
                ("default",),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO notification_channel_settings (settings_key, payload) VALUES (?, ?)",
                    ("default", json.dumps(_DEFAULT_SETTINGS, ensure_ascii=False)),
                )

    def _row_to_channel(self, row: tuple[Any, ...]) -> dict[str, Any]:
        metadata_raw = row[7]
        metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        return {
            "channel_id": row[0],
            "name": row[1],
            "channel_type": row[2],
            "endpoint_url": row[3],
            "secret": row[4] or "",
            "enabled": bool(row[5]),
            "sort_order": int(row[6] or 0),
            "metadata": metadata,
            "created_at": row[8],
            "updated_at": row[9],
        }

    def list_channels(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT channel_id, name, channel_type, endpoint_url, secret, enabled,
                       sort_order, metadata, created_at, updated_at
                FROM notification_channels
                """
            ).fetchall()
        return _sort_channels([self._row_to_channel(row) for row in rows])

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT channel_id, name, channel_type, endpoint_url, secret, enabled,
                       sort_order, metadata, created_at, updated_at
                FROM notification_channels WHERE channel_id = ?
                """,
                (channel_id,),
            ).fetchone()
        return self._row_to_channel(row) if row else None

    def upsert_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel.get("channel_id") or "").strip()
        existing = self.get_channel(channel_id) if channel_id else None
        if existing is None:
            name = str(channel.get("name") or "").strip()
            existing = next((item for item in self.list_channels() if item.get("name") == name), None)
        normalized = _normalize_channel_payload(channel, existing=existing)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO notification_channels (
                    channel_id, name, channel_type, endpoint_url, secret, enabled,
                    sort_order, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized["channel_id"],
                    normalized["name"],
                    normalized["channel_type"],
                    normalized["endpoint_url"],
                    normalized["secret"],
                    1 if normalized["enabled"] else 0,
                    normalized["sort_order"],
                    json.dumps(normalized["metadata"], ensure_ascii=False),
                    normalized["created_at"],
                    normalized["updated_at"],
                ),
            )
        return normalized

    def delete_channel(self, channel_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM notification_channels WHERE channel_id = ?", (channel_id,))

    def get_settings(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM notification_channel_settings WHERE settings_key = ?",
                ("default",),
            ).fetchone()
        if row is None:
            return dict(_DEFAULT_SETTINGS)
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            return dict(_DEFAULT_SETTINGS)
        payload.setdefault("broadcast_enabled", True)
        return payload

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        settings = self.get_settings()
        settings.update(dict(patch))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO notification_channel_settings (settings_key, payload)
                VALUES (?, ?)
                """,
                ("default", json.dumps(settings, ensure_ascii=False)),
            )
        return settings


class MysqlNotificationChannelStore:
    def __init__(self, config: MysqlConnectConfig) -> None:
        self.config = config
        self._init()

    def _connect(self):
        return mysql_connection(self.config)

    def _init(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notification_channels (
                        channel_id VARCHAR(64) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL UNIQUE,
                        channel_type VARCHAR(32) NOT NULL,
                        endpoint_url TEXT NOT NULL,
                        secret TEXT,
                        enabled TINYINT(1) NOT NULL DEFAULT 1,
                        sort_order INT NOT NULL DEFAULT 0,
                        metadata JSON,
                        created_at VARCHAR(64) NOT NULL,
                        updated_at VARCHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notification_channel_settings (
                        settings_key VARCHAR(64) PRIMARY KEY,
                        payload JSON NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    "SELECT payload FROM notification_channel_settings WHERE settings_key = %s",
                    ("default",),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        """
                        INSERT INTO notification_channel_settings (settings_key, payload)
                        VALUES (%s, %s)
                        """,
                        ("default", json.dumps(_DEFAULT_SETTINGS, ensure_ascii=False)),
                    )

    def _decode_json(self, raw: Any) -> dict[str, Any]:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if isinstance(raw, str):
            raw = json.loads(raw)
        return raw if isinstance(raw, dict) else {}

    def _row_to_channel(self, row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "channel_id": row[0],
            "name": row[1],
            "channel_type": row[2],
            "endpoint_url": row[3],
            "secret": row[4] or "",
            "enabled": bool(row[5]),
            "sort_order": int(row[6] or 0),
            "metadata": self._decode_json(row[7]),
            "created_at": row[8],
            "updated_at": row[9],
        }

    def list_channels(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT channel_id, name, channel_type, endpoint_url, secret, enabled,
                           sort_order, metadata, created_at, updated_at
                    FROM notification_channels
                    """
                )
                rows = cur.fetchall()
        return _sort_channels([self._row_to_channel(row) for row in rows])

    def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT channel_id, name, channel_type, endpoint_url, secret, enabled,
                           sort_order, metadata, created_at, updated_at
                    FROM notification_channels WHERE channel_id = %s
                    """,
                    (channel_id,),
                )
                row = cur.fetchone()
        return self._row_to_channel(row) if row else None

    def upsert_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel.get("channel_id") or "").strip()
        existing = self.get_channel(channel_id) if channel_id else None
        if existing is None:
            name = str(channel.get("name") or "").strip()
            existing = next((item for item in self.list_channels() if item.get("name") == name), None)
        normalized = _normalize_channel_payload(channel, existing=existing)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO notification_channels (
                        channel_id, name, channel_type, endpoint_url, secret, enabled,
                        sort_order, metadata, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        normalized["channel_id"],
                        normalized["name"],
                        normalized["channel_type"],
                        normalized["endpoint_url"],
                        normalized["secret"],
                        1 if normalized["enabled"] else 0,
                        normalized["sort_order"],
                        json.dumps(normalized["metadata"], ensure_ascii=False),
                        normalized["created_at"],
                        normalized["updated_at"],
                    ),
                )
        return normalized

    def delete_channel(self, channel_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM notification_channels WHERE channel_id = %s", (channel_id,))

    def get_settings(self) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payload FROM notification_channel_settings WHERE settings_key = %s",
                    ("default",),
                )
                row = cur.fetchone()
        if row is None:
            return dict(_DEFAULT_SETTINGS)
        payload = self._decode_json(row[0])
        payload.setdefault("broadcast_enabled", True)
        return payload

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        settings = self.get_settings()
        settings.update(dict(patch))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO notification_channel_settings (settings_key, payload)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE payload = VALUES(payload)
                    """,
                    ("default", json.dumps(settings, ensure_ascii=False)),
                )
        return settings


def build_notification_channel_store(
    repo_root: Path,
    *,
    settings: RootSeekerSettings | None = None,
) -> NotificationChannelStore:
    cfg = settings or RootSeekerSettings()
    (repo_root / "data" / "admin").mkdir(parents=True, exist_ok=True)
    store_kind = resolve_notification_channel_store(cfg)
    if store_kind == "mysql":
        return MysqlNotificationChannelStore(mysql_config_from_settings(cfg))
    if store_kind == "sqlite":
        path = Path(cfg.notification_channel_sqlite_path)
        if not path.is_absolute():
            path = repo_root / path
        return SqliteNotificationChannelStore(path)
    path = Path(cfg.notification_channel_file)
    if not path.is_absolute():
        path = repo_root / path
    return FileNotificationChannelStore(path)


def migrate_legacy_callbacks_from_admin(
    admin_data: dict[str, Any],
    channel_store: NotificationChannelStore,
) -> dict[str, Any]:
    """Import legacy AdminConfigStore callbacks into NotificationChannelStore once."""
    callbacks = [item for item in admin_data.get("callbacks", []) if isinstance(item, dict)]
    if not callbacks or channel_store.list_channels():
        return admin_data
    for item in callbacks:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        channel_store.upsert_channel(
            {
                "name": str(item.get("name") or "").strip() or f"legacy-{uuid.uuid4().hex[:8]}",
                "channel_type": str(item.get("channel") or "webhook"),
                "endpoint_url": url,
                "secret": str(item.get("secret") or ""),
                "enabled": bool(item.get("enabled", True)),
                "metadata": dict(item.get("metadata") or {}),
            }
        )
    updated = dict(admin_data)
    updated["callbacks"] = []
    return updated
