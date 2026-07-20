"""MySQL connection helpers (PyMySQL) with a small process-local pool."""

from __future__ import annotations

import json
import queue
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

__all__ = [
    "MysqlConnectConfig",
    "MysqlConnectionPool",
    "connect_mysql",
    "decode_mysql_json",
    "get_mysql_pool",
    "mysql_config_from_settings",
    "mysql_connection",
]


@dataclass(frozen=True)
class MysqlConnectConfig:
    host: str = "127.0.0.1"
    port: int = 3306
    user: str = "rootseeker"
    password: str = "rootseeker"
    database: str = "rootseeker"
    charset: str = "utf8mb4"
    connect_timeout: int = 10
    pool_size: int = 8

    def as_connect_kwargs(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": self.charset,
            "autocommit": True,
            "connect_timeout": self.connect_timeout,
            "cursorclass": None,  # filled in connect_mysql
        }

    def pool_key(self) -> tuple[Any, ...]:
        return (
            self.host,
            self.port,
            self.user,
            self.password,
            self.database,
            self.charset,
            self.connect_timeout,
            self.pool_size,
        )


def mysql_config_from_settings(settings: Any) -> MysqlConnectConfig:
    return MysqlConnectConfig(
        host=str(getattr(settings, "mysql_host", "127.0.0.1")),
        port=int(getattr(settings, "mysql_port", 3306)),
        user=str(getattr(settings, "mysql_user", "rootseeker")),
        password=str(getattr(settings, "mysql_password", "rootseeker")),
        database=str(getattr(settings, "mysql_database", "rootseeker")),
        charset=str(getattr(settings, "mysql_charset", "utf8mb4")),
        connect_timeout=int(getattr(settings, "mysql_connect_timeout", 10)),
        pool_size=int(getattr(settings, "mysql_pool_size", 8)),
    )


def connect_mysql(config: MysqlConnectConfig):
    """Open a PyMySQL connection. Raises ImportError if PyMySQL is missing."""
    import pymysql
    from pymysql.cursors import Cursor

    kwargs = config.as_connect_kwargs()
    kwargs["cursorclass"] = Cursor
    return pymysql.connect(**kwargs)


def decode_mysql_json(raw: Any, *, default: Any = None) -> Any:
    """Normalize PyMySQL JSON column values (dict/list/str/bytes/None)."""
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    if isinstance(raw, str):
        if not raw:
            return default
        return json.loads(raw)
    raise TypeError(f"unexpected MySQL JSON payload type: {type(raw)!r}")


class MysqlConnectionPool:
    """Simple bounded connection pool (process-local)."""

    def __init__(self, config: MysqlConnectConfig) -> None:
        self._config = config
        self._size = max(1, int(config.pool_size))
        self._pool: queue.Queue[Any] = queue.Queue(maxsize=self._size)
        self._created = 0
        self._lock = threading.Lock()

    def _create(self):
        return connect_mysql(self._config)

    def _alive(self, conn: Any) -> bool:
        try:
            conn.ping(reconnect=True)
            return True
        except Exception:  # noqa: BLE001
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            return False

    def acquire(self, *, timeout: float = 30.0):
        while True:
            try:
                conn = self._pool.get_nowait()
            except queue.Empty:
                break
            if self._alive(conn):
                return conn

        with self._lock:
            if self._created < self._size:
                self._created += 1
                return self._create()

        conn = self._pool.get(timeout=timeout)
        if not self._alive(conn):
            return self._create()
        return conn

    def release(self, conn: Any) -> None:
        if conn is None:
            return
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


_POOLS: dict[tuple[Any, ...], MysqlConnectionPool] = {}
_POOLS_LOCK = threading.Lock()


def get_mysql_pool(config: MysqlConnectConfig) -> MysqlConnectionPool:
    key = config.pool_key()
    with _POOLS_LOCK:
        pool = _POOLS.get(key)
        if pool is None:
            pool = MysqlConnectionPool(config)
            _POOLS[key] = pool
        return pool


@contextmanager
def mysql_connection(config: MysqlConnectConfig) -> Iterator[Any]:
    """Borrow a pooled connection; return it on exit (does not close)."""
    pool = get_mysql_pool(config)
    conn = pool.acquire()
    try:
        yield conn
    finally:
        pool.release(conn)
