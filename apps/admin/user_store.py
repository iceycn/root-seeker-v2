from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.mysql_conn import MysqlConnectConfig, mysql_config_from_settings, mysql_connection

__all__ = [
    "MemoryUserStore",
    "MysqlUserStore",
    "SqliteUserStore",
    "UserAlreadyExists",
    "UsersAlreadyExist",
    "UserStore",
    "build_user_store",
    "public_user",
]


class UserAlreadyExists(Exception):
    """Username unique constraint violated."""


class UsersAlreadyExist(Exception):
    """Bootstrap is only allowed when the users table is empty."""


class UserStore(Protocol):
    def list_users(self) -> list[dict[str, Any]]: ...

    def count(self) -> int: ...

    def get_by_id(self, user_id: str) -> dict[str, Any] | None: ...

    def get_by_username(self, username: str) -> dict[str, Any] | None: ...

    def create(self, username: str, password_hash: str) -> dict[str, Any]: ...

    def create_first(self, username: str, password_hash: str) -> dict[str, Any]: ...

    def update_password_hash(self, user_id: str, password_hash: str) -> dict[str, Any] | None: ...

    def delete(self, user_id: str) -> bool: ...


def public_user(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "username": record["username"],
        "created_at": record["created_at"],
    }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_user(username: str, password_hash: str) -> dict[str, Any]:
    stamp = _now()
    return {
        "id": str(uuid.uuid4()),
        "username": username,
        "password_hash": password_hash,
        "created_at": stamp,
        "updated_at": stamp,
    }


def _row_to_user(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "password_hash": row[2],
        "created_at": row[3],
        "updated_at": row[4],
    }


class MemoryUserStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._users: dict[str, dict[str, Any]] = {}

    def list_users(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._users.values()]

    def count(self) -> int:
        with self._lock:
            return len(self._users)

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._users.get(user_id)
            return dict(item) if item else None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        with self._lock:
            for item in self._users.values():
                if item["username"] == username:
                    return dict(item)
        return None

    def create(self, username: str, password_hash: str) -> dict[str, Any]:
        with self._lock:
            if any(item["username"] == username for item in self._users.values()):
                raise UserAlreadyExists(username)
            record = _new_user(username, password_hash)
            self._users[record["id"]] = record
            return dict(record)

    def create_first(self, username: str, password_hash: str) -> dict[str, Any]:
        with self._lock:
            if self._users:
                raise UsersAlreadyExist()
            record = _new_user(username, password_hash)
            self._users[record["id"]] = record
            return dict(record)

    def update_password_hash(self, user_id: str, password_hash: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._users.get(user_id)
            if item is None:
                return None
            item["password_hash"] = password_hash
            item["updated_at"] = _now()
            return dict(item)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            return self._users.pop(user_id, None) is not None


class SqliteUserStore:
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
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, username, password_hash, created_at, updated_at FROM users ORDER BY created_at ASC"
            ).fetchall()
        return [_row_to_user(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, created_at, updated_at FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        return _row_to_user(row) if row else None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, created_at, updated_at FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return _row_to_user(row) if row else None

    def create(self, username: str, password_hash: str) -> dict[str, Any]:
        record = _new_user(username, password_hash)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users (id, username, password_hash, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        record["id"],
                        record["username"],
                        record["password_hash"],
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExists(username) from exc
        return record

    def create_first(self, username: str, password_hash: str) -> dict[str, Any]:
        record = _new_user(username, password_hash)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO users (id, username, password_hash, created_at, updated_at)
                    SELECT ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (SELECT 1 FROM users)
                    """,
                    (
                        record["id"],
                        record["username"],
                        record["password_hash"],
                        record["created_at"],
                        record["updated_at"],
                    ),
                )
                if cur.rowcount == 0:
                    raise UsersAlreadyExist()
        except sqlite3.IntegrityError as exc:
            raise UserAlreadyExists(username) from exc
        return record

    def update_password_hash(self, user_id: str, password_hash: str) -> dict[str, Any] | None:
        stamp = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, stamp, user_id),
            )
            if cur.rowcount == 0:
                return None
        return self.get_by_id(user_id)

    def delete(self, user_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cur.rowcount > 0


class MysqlUserStore:
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
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(36) PRIMARY KEY,
                        username VARCHAR(64) NOT NULL UNIQUE COLLATE utf8mb4_bin,
                        password_hash VARCHAR(255) NOT NULL,
                        created_at VARCHAR(64) NOT NULL,
                        updated_at VARCHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, username, password_hash, created_at, updated_at FROM users ORDER BY created_at ASC"
                )
                rows = cur.fetchall()
        return [_row_to_user(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_by_id(self, user_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, username, password_hash, created_at, updated_at FROM users WHERE id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
        return _row_to_user(row) if row else None

    def get_by_username(self, username: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, username, password_hash, created_at, updated_at FROM users WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
        return _row_to_user(row) if row else None

    def create(self, username: str, password_hash: str) -> dict[str, Any]:
        record = _new_user(username, password_hash)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO users (id, username, password_hash, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            record["id"],
                            record["username"],
                            record["password_hash"],
                            record["created_at"],
                            record["updated_at"],
                        ),
                    )
        except Exception as exc:
            name = type(exc).__name__
            if "IntegrityError" in name or "Integrity" in name:
                raise UserAlreadyExists(username) from exc
            raise
        return record

    def create_first(self, username: str, password_hash: str) -> dict[str, Any]:
        record = _new_user(username, password_hash)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO users (id, username, password_hash, created_at, updated_at)
                        SELECT %s, %s, %s, %s, %s FROM (SELECT 1 AS ok) AS dummy
                        WHERE NOT EXISTS (SELECT 1 FROM users)
                        """,
                        (
                            record["id"],
                            record["username"],
                            record["password_hash"],
                            record["created_at"],
                            record["updated_at"],
                        ),
                    )
                    if cur.rowcount == 0:
                        raise UsersAlreadyExist()
        except UsersAlreadyExist:
            raise
        except Exception as exc:
            name = type(exc).__name__
            if "IntegrityError" in name or "Integrity" in name:
                raise UserAlreadyExists(username) from exc
            raise
        return record

    def update_password_hash(self, user_id: str, password_hash: str) -> dict[str, Any] | None:
        stamp = _now()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s",
                    (password_hash, stamp, user_id),
                )
                if cur.rowcount == 0:
                    return None
        return self.get_by_id(user_id)

    def delete(self, user_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                return cur.rowcount > 0


def build_user_store(
    repo_root: Path,
    *,
    settings: RootSeekerSettings | None = None,
) -> UserStore:
    cfg = settings or RootSeekerSettings()
    if cfg.storage_backend == "mysql":
        return MysqlUserStore(mysql_config_from_settings(cfg))
    if cfg.storage_backend == "sqlite":
        path = Path(cfg.admin_users_sqlite_path)
        if not path.is_absolute():
            path = repo_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteUserStore(path)
    return MemoryUserStore()

