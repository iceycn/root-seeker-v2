# Admin Login and User Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect the Admin console (`:8010`) with a login page, Cookie-backed in-memory sessions, a `users` table (no plaintext passwords), and a same-permission user management UI that can change passwords but never usernames.

**Architecture:** FastAPI middleware on `apps/admin` validates HttpOnly Cookie `rootseeker_admin_session` against a process-local `SessionStore`. Persistent users live in `UserStore` (memory / sqlite / mysql following `ROOTSEEKER_STORAGE_BACKEND`). Passwords are bcrypt hashes. Empty table → bootstrap first account; deleting all users returns to bootstrap.

**Tech Stack:** Python 3.11, FastAPI, bcrypt, pytest, React + Ant Design (`apps/admin-web`).

**Spec:** `docs/superpowers/specs/2026-09-15-admin-login-user-management-design.md`

## Global Constraints

- Protect Admin only (`apps/admin`). Do not change `apps/api` webhook / cases / Gateway token auth.
- All logged-in users have the same permissions; no role column.
- One persistent table: `users`. Sessions are in-memory only (lost on process restart).
- Cookie name is exactly `rootseeker_admin_session`; HttpOnly; SameSite=Lax; Path=/; no Secure flag; TTL 12 hours.
- Passwords: bcrypt; 8–128 chars; never log, return, or store plaintext; list/detail JSON must omit `password_hash`.
- Username: 3–64 chars, `^[A-Za-z0-9._-]+$`, case-sensitive unique, immutable (no update API).
- Empty user table: login page becomes bootstrap; `POST /api/auth/login` still returns 401 `用户名或密码错误`.
- Users may delete themselves and the last user; then `needs_bootstrap` is true.
- Public paths: `GET /healthz`, `GET /login`, `GET /assets/*`, `GET /api/auth/status`, `POST /api/auth/login`, `POST /api/auth/bootstrap`, `POST /api/auth/logout`.
- Copy strings: `未登录`, `用户名或密码错误`, `已存在用户，请登录`, `用户名已存在`, `旧密码不正确`, `新密码不能与旧密码相同`, `用户不存在`.
- Do not commit unless the user explicitly asks (skip Commit steps until then).
- Branch: `v1.2.0`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `apps/admin/passwords.py` | bcrypt `hash_password` / `verify_password` |
| `apps/admin/user_rules.py` | username / password validation messages |
| `apps/admin/user_store.py` | `UserStore` protocol + memory/sqlite/mysql + `build_user_store` |
| `apps/admin/session_store.py` | in-memory session dict + lock + TTL |
| `apps/admin/auth_middleware.py` | Cookie interceptor; 302 pages / 401 APIs |
| `apps/admin/main.py` | wire stores/middleware; auth + users routes; SPA `/login` `/users` |
| `apps/admin-web/src/LoginPage.tsx` | full-screen login / bootstrap card |
| `apps/admin-web/src/UsersPage.tsx` | user table + create modal |
| `apps/admin-web/src/App.tsx` | `/login` gate, users menu, topbar password/logout, 401 redirect |
| `apps/admin-web/src/App.css` | login layout |
| `mysql/init/01_schema.sql` | `users` table |
| `rootseeker/infra_core/settings.py` | `admin_users_sqlite_path` |
| `pyproject.toml` | `bcrypt` dependency |
| `tests/support/admin_client.py` | bootstrap helper so existing Admin tests keep working |
| `tests/unit/apps/test_admin_user_store.py` | store + hash persistence |
| `tests/unit/apps/test_admin_auth.py` | middleware and HTTP auth/users flows |
| `docs/releases/v1.2.0.md` | upgrade notes |
| `docs/business-logic/18-apps-api-admin-cli.md` | document auth routes |

---

### Task 1: bcrypt password helpers

**Files:**
- Create: `apps/admin/passwords.py`
- Create: `apps/admin/user_rules.py`
- Modify: `pyproject.toml` (add `bcrypt>=4.2.0` to `[project] dependencies`)
- Test: `tests/unit/apps/test_admin_user_store.py` (password section first; file grows in later tasks)

**Interfaces:**
- Produces: `hash_password(plain: str) -> str`
- Produces: `verify_password(plain: str, password_hash: str) -> bool`
- Produces: `username_error(username: str) -> str | None`
- Produces: `password_error(password: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/apps/test_admin_user_store.py`:

```python
from __future__ import annotations

from apps.admin.passwords import hash_password, verify_password
from apps.admin.user_rules import password_error, username_error


def test_hash_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("password12")
    assert hashed != "password12"
    assert "password12" not in hashed
    assert verify_password("password12", hashed)
    assert not verify_password("wrong-password", hashed)


def test_same_password_hashes_differ() -> None:
    assert hash_password("password12") != hash_password("password12")


def test_username_and_password_rules() -> None:
    assert username_error("ab") is not None
    assert username_error("admin") is None
    assert username_error("Bad User") is not None
    assert password_error("short") is not None
    assert password_error("password12") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/apps/test_admin_user_store.py::test_hash_is_not_plaintext_and_verifies -v`

Expected: FAIL with import error (`apps.admin.passwords` missing) or `bcrypt` missing.

- [ ] **Step 3: Add dependency and minimal implementation**

In `pyproject.toml` dependencies, add `"bcrypt>=4.2.0",` after `"PyMySQL>=1.1.0",`.

Then `uv lock` / `uv sync` so the env has bcrypt.

Create `apps/admin/passwords.py`:

```python
"""Password hashing for Admin users. Never store or log plaintext."""

from __future__ import annotations

import bcrypt

__all__ = ["hash_password", "verify_password"]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
```

Create `apps/admin/user_rules.py`:

```python
"""Username / password input rules for Admin users."""

from __future__ import annotations

import re

__all__ = ["USERNAME_RE", "password_error", "username_error"]

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def username_error(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(username or ""):
        return "用户名须为 3–64 位字母、数字、点、下划线或连字符"
    return None


def password_error(password: str) -> str | None:
    if not (8 <= len(password or "") <= 128):
        return "密码长度须为 8–128 位"
    return None
```

- [ ] **Step 4: Run tests and make sure they pass**

Run: `pytest tests/unit/apps/test_admin_user_store.py -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit** (skip unless the user asked)

```bash
git add pyproject.toml uv.lock apps/admin/passwords.py apps/admin/user_rules.py tests/unit/apps/test_admin_user_store.py
git commit -m "feat(admin): add bcrypt password helpers"
```

---

### Task 2: Memory UserStore

**Files:**
- Create: `apps/admin/user_store.py` (protocol + Memory + exceptions; sqlite/mysql added in Task 3)
- Test: `tests/unit/apps/test_admin_user_store.py`

**Interfaces:**
- Consumes: `hash_password` from Task 1 (tests hash before `create`)
- Produces: `UserAlreadyExists`, `UserStore` protocol, `MemoryUserStore`, `public_user(record: dict) -> dict`

`UserStore` methods:

```python
class UserStore(Protocol):
    def list_users(self) -> list[dict[str, Any]]: ...
    def count(self) -> int: ...
    def get_by_id(self, user_id: str) -> dict[str, Any] | None: ...
    def get_by_username(self, username: str) -> dict[str, Any] | None: ...
    def create(self, username: str, password_hash: str) -> dict[str, Any]: ...
    def update_password_hash(self, user_id: str, password_hash: str) -> dict[str, Any] | None: ...
    def delete(self, user_id: str) -> bool: ...
```

Record keys: `id`, `username`, `password_hash`, `created_at`, `updated_at`.  
`public_user` returns `{id, username, created_at}` only.

- [ ] **Step 1: Write the failing tests** (append to `test_admin_user_store.py`)

```python
from apps.admin.user_store import MemoryUserStore, UserAlreadyExists, public_user


def test_memory_store_create_list_delete() -> None:
    store = MemoryUserStore()
    hashed = hash_password("password12")
    user = store.create("alice", hashed)
    assert user["username"] == "alice"
    assert user["password_hash"] != "password12"
    assert store.count() == 1
    listed = store.list_users()
    assert listed[0]["username"] == "alice"
    assert "password_hash" not in public_user(listed[0])
    assert store.get_by_username("alice")["id"] == user["id"]
    assert store.delete(user["id"]) is True
    assert store.count() == 0


def test_memory_store_duplicate_username() -> None:
    store = MemoryUserStore()
    store.create("alice", hash_password("password12"))
    try:
        store.create("alice", hash_password("password12"))
        raise AssertionError("expected UserAlreadyExists")
    except UserAlreadyExists:
        pass


def test_memory_store_update_password_keeps_username() -> None:
    store = MemoryUserStore()
    user = store.create("alice", hash_password("password12"))
    updated = store.update_password_hash(user["id"], hash_password("password13"))
    assert updated is not None
    assert updated["username"] == "alice"
    assert verify_password("password13", updated["password_hash"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/apps/test_admin_user_store.py::test_memory_store_create_list_delete -v`

Expected: FAIL import `MemoryUserStore`

- [ ] **Step 3: Write minimal implementation**

Create `apps/admin/user_store.py`:

```python
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
    "UserStore",
    "build_user_store",
    "public_user",
]


class UserAlreadyExists(Exception):
    """Username unique constraint violated."""


class UserStore(Protocol):
    def list_users(self) -> list[dict[str, Any]]: ...

    def count(self) -> int: ...

    def get_by_id(self, user_id: str) -> dict[str, Any] | None: ...

    def get_by_username(self, username: str) -> dict[str, Any] | None: ...

    def create(self, username: str, password_hash: str) -> dict[str, Any]: ...

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
```

Leave `SqliteUserStore` / `MysqlUserStore` / `build_user_store` unimplemented until Task 3 (do not add broken names to `__all__` yet — drop those three from `__all__` until Task 3, and do not import mysql helpers yet).

Task 2 `__all__` and imports should only include Memory + protocol until Task 3. Use this `__all__` in Task 2:

```python
__all__ = ["MemoryUserStore", "UserAlreadyExists", "UserStore", "public_user"]
```

And do **not** import sqlite/mysql in Task 2.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/apps/test_admin_user_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (skip unless asked)

```bash
git add apps/admin/user_store.py tests/unit/apps/test_admin_user_store.py
git commit -m "feat(admin): add in-memory user store"
```

---

### Task 3: SQLite / MySQL UserStore + schema

**Files:**
- Modify: `apps/admin/user_store.py` (add sqlite/mysql + `build_user_store`)
- Modify: `rootseeker/infra_core/settings.py` (add `admin_users_sqlite_path: str = "data/admin/users.sqlite"`)
- Modify: `mysql/init/01_schema.sql`
- Test: `tests/unit/apps/test_admin_user_store.py`

**Interfaces:**
- Consumes: `RootSeekerSettings.storage_backend`
- Produces: `SqliteUserStore`, `MysqlUserStore`, `build_user_store(repo_root: Path, *, settings: RootSeekerSettings | None = None) -> UserStore`

`build_user_store`: `mysql` → `MysqlUserStore`; `sqlite` → `SqliteUserStore(repo_root / settings.admin_users_sqlite_path)` (absolute path if already absolute); else `MemoryUserStore`.

SQL table (both engines conceptually):

```sql
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at VARCHAR(64) NOT NULL,
    updated_at VARCHAR(64) NOT NULL
)
```

SQLite uses `TEXT` instead of `VARCHAR`. MySQL adds `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4`.

- [ ] **Step 1: Write the failing sqlite test**

```python
from apps.admin.user_store import SqliteUserStore, build_user_store
from rootseeker.infra_core.settings import RootSeekerSettings


def test_sqlite_store_roundtrip(tmp_path) -> None:
    store = SqliteUserStore(tmp_path / "users.sqlite")
    store.create("bob", hash_password("password12"))
    again = SqliteUserStore(tmp_path / "users.sqlite")
    assert again.count() == 1
    assert again.get_by_username("bob")["username"] == "bob"
    try:
        again.create("bob", hash_password("password12"))
        raise AssertionError("expected UserAlreadyExists")
    except UserAlreadyExists:
        pass


def test_build_user_store_follows_memory_backend(tmp_path) -> None:
    settings = RootSeekerSettings(storage_backend="memory")
    store = build_user_store(tmp_path, settings=settings)
    assert isinstance(store, MemoryUserStore)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/apps/test_admin_user_store.py::test_sqlite_store_roundtrip -v`

Expected: FAIL import `SqliteUserStore`

- [ ] **Step 3: Implement sqlite/mysql + builder + schema**

Append to `user_store.py` (and restore mysql imports + `__all__` names from the Task 2 sketch).

`SqliteUserStore`: `_connect` → `sqlite3.connect`; `_init` runs CREATE TABLE; `create` catches `sqlite3.IntegrityError` → `UserAlreadyExists`; `list_users` `SELECT id, username, password_hash, created_at, updated_at FROM users ORDER BY created_at ASC`; map rows to dicts.

`MysqlUserStore`: `_init` CREATE TABLE IF NOT EXISTS as in spec; `create` uses `%s` placeholders; catch `pymysql.err.IntegrityError` → `UserAlreadyExists`:

```python
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
```

Add to `mysql/init/01_schema.sql` after `error_chat_history`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at VARCHAR(64) NOT NULL,
    updated_at VARCHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

Add setting:

```python
admin_users_sqlite_path: str = "data/admin/users.sqlite"
```

`build_user_store`:

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/apps/test_admin_user_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (skip unless asked)

```bash
git add apps/admin/user_store.py rootseeker/infra_core/settings.py mysql/init/01_schema.sql tests/unit/apps/test_admin_user_store.py
git commit -m "feat(admin): persist users in sqlite/mysql"
```

---

### Task 4: In-memory SessionStore

**Files:**
- Create: `apps/admin/session_store.py`
- Test: `tests/unit/apps/test_admin_auth.py` (session section first)

**Interfaces:**
- Produces: `SESSION_COOKIE_NAME = "rootseeker_admin_session"`
- Produces: `SESSION_TTL_SECONDS = 12 * 3600`
- Produces: `SessionRecord` dataclass `user_id: str`, `username: str`, `expires_at: datetime`
- Produces: `SessionStore.create(user_id, username) -> str` (session_id)
- Produces: `SessionStore.get(session_id) -> SessionRecord | None` (deletes if expired)
- Produces: `SessionStore.delete(session_id) -> None`
- Produces: `SessionStore.delete_by_user_id(user_id) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/apps/test_admin_auth.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apps.admin.session_store import SESSION_TTL_SECONDS, SessionStore


def test_session_roundtrip_and_delete() -> None:
    store = SessionStore()
    sid = store.create("u1", "alice")
    rec = store.get(sid)
    assert rec is not None
    assert rec.user_id == "u1"
    assert rec.username == "alice"
    store.delete(sid)
    assert store.get(sid) is None


def test_session_expires() -> None:
    store = SessionStore()
    sid = store.create("u1", "alice")
    rec = store.get(sid)
    assert rec is not None
    rec.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert store.get(sid) is None


def test_new_store_does_not_see_old_id() -> None:
    first = SessionStore()
    sid = first.create("u1", "alice")
    second = SessionStore()
    assert second.get(sid) is None


def test_delete_by_user_id() -> None:
    store = SessionStore()
    sid = store.create("u1", "alice")
    store.delete_by_user_id("u1")
    assert store.get(sid) is None
```

Also assert `SESSION_TTL_SECONDS == 12 * 3600` in `test_session_roundtrip_and_delete`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/apps/test_admin_auth.py::test_session_roundtrip_and_delete -v`

Expected: FAIL import

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

__all__ = ["SESSION_COOKIE_NAME", "SESSION_TTL_SECONDS", "SessionRecord", "SessionStore"]

SESSION_COOKIE_NAME = "rootseeker_admin_session"
SESSION_TTL_SECONDS = 12 * 3600


@dataclass
class SessionRecord:
    user_id: str
    username: str
    expires_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, user_id: str, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        record = SessionRecord(
            user_id=user_id,
            username=username,
            expires_at=datetime.now(UTC) + timedelta(seconds=SESSION_TTL_SECONDS),
        )
        with self._lock:
            self._sessions[session_id] = record
        return session_id

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                return None
            if datetime.now(UTC) >= record.expires_at:
                self._sessions.pop(session_id, None)
                return None
            return record

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def delete_by_user_id(self, user_id: str) -> None:
        with self._lock:
            stale = [key for key, rec in self._sessions.items() if rec.user_id == user_id]
            for key in stale:
                self._sessions.pop(key, None)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/apps/test_admin_auth.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (skip unless asked)

```bash
git add apps/admin/session_store.py tests/unit/apps/test_admin_auth.py
git commit -m "feat(admin): add in-memory admin session store"
```

---

### Task 5: Auth middleware, auth routes, keep existing Admin tests green

**Files:**
- Create: `apps/admin/auth_middleware.py`
- Create: `tests/support/admin_client.py`
- Modify: `apps/admin/main.py` (`create_app` wire + auth endpoints + SPA `/login`)
- Modify: `tests/unit/apps/test_admin_main.py` (fixture + unauthenticated page assertions)
- Modify: `tests/unit/apps/test_admin_cron_jobs_api.py`
- Modify: `tests/unit/apps/test_admin_message_templates.py`
- Modify: `tests/unit/skill_system/test_skill_env_on_run.py`
- Test: `tests/unit/apps/test_admin_auth.py`

**Interfaces:**
- Consumes: `UserStore`, `SessionStore`, `hash_password`, `verify_password`, `username_error`, `password_error`
- Produces: middleware that sets `request.state.admin_user` to `SessionRecord` when valid
- Produces HTTP:
  - `GET /api/auth/status` → `{authenticated, needs_bootstrap, user}`
  - `POST /api/auth/bootstrap` `{username, password}`
  - `POST /api/auth/login` `{username, password}`
  - `POST /api/auth/logout`
  - `GET /api/auth/me`

Helper `tests/support/admin_client.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from apps.admin.main import create_app

TEST_ADMIN_USERNAME = "testadmin"
TEST_ADMIN_PASSWORD = "password12"


def make_admin_client(
    repo_root: Path,
    *,
    authenticated: bool = True,
    **kwargs: Any,
) -> TestClient:
    client = TestClient(create_app(repo_root, **kwargs), follow_redirects=False)
    if authenticated:
        resp = client.post(
            "/api/auth/bootstrap",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert resp.status_code == 200, resp.text
    return client


def bootstrap_client(client: TestClient) -> None:
    resp = client.post(
        "/api/auth/bootstrap",
        json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
```

Replace `TestClient(create_app(...))` in existing admin HTTP tests with `make_admin_client(...)`. Tests that need `app.state` should:

```python
app = create_app(tmp_path)
client = TestClient(app, follow_redirects=False)
bootstrap_client(client)
```

Rewrite `test_admin_health_status_and_page`:

- Unauthenticated: `/healthz` 200; `/admin` 302 Location contains `/login`; `/api/status` 401 `未登录`; `/api/auth/status` 200 `needs_bootstrap true`.
- Authenticated via helper: `/admin` 200 (SPA or fallback); `/api/status` 200 with `skills_total`.

- [ ] **Step 1: Write failing HTTP tests** (append to `test_admin_auth.py`)

```python
from fastapi.testclient import TestClient

from apps.admin.main import create_app
from apps.admin.session_store import SESSION_COOKIE_NAME


def test_unauthenticated_api_and_page(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    assert client.get("/healthz").status_code == 200
    status = client.get("/api/auth/status")
    assert status.status_code == 200
    assert status.json()["needs_bootstrap"] is True
    assert status.json()["authenticated"] is False
    settings = client.get("/api/settings")
    assert settings.status_code == 401
    assert settings.json()["detail"] == "未登录"
    page = client.get("/overview")
    assert page.status_code == 302
    assert "/login" in page.headers["location"]


def test_bootstrap_sets_cookie_then_second_bootstrap_conflicts(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    first = client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password12"})
    assert first.status_code == 200
    assert SESSION_COOKIE_NAME in first.cookies
    second = client.post("/api/auth/bootstrap", json={"username": "other", "password": "password12"})
    assert second.status_code == 409
    assert second.json()["detail"] == "已存在用户，请登录"


def test_login_success_and_wrong_password(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password12"})
    client.post("/api/auth/logout")
    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong-password-1"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "用户名或密码错误"
    assert SESSION_COOKIE_NAME not in bad.cookies
    empty_login = TestClient(create_app(tmp_path), follow_redirects=False)
    denied = empty_login.post("/api/auth/login", json={"username": "admin", "password": "password12"})
    assert denied.status_code == 401
    ok = client.post("/api/auth/login", json={"username": "admin", "password": "password12"})
    assert ok.status_code == 200
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "admin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/apps/test_admin_auth.py::test_unauthenticated_api_and_page -v`

Expected: FAIL (`/api/settings` currently 200, `/overview` currently 200)

- [ ] **Step 3: Implement middleware + routes + helper + migrate existing tests**

`apps/admin/auth_middleware.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from apps.admin.session_store import SESSION_COOKIE_NAME, SessionStore
from apps.admin.user_store import UserStore

PUBLIC_EXACT = {
    ("GET", "/healthz"),
    ("GET", "/login"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/bootstrap"),
    ("POST", "/api/auth/logout"),
}


def is_public(method: str, path: str) -> bool:
    if path.startswith("/assets/"):
        return True
    return (method.upper(), path) in PUBLIC_EXACT


def AdminAuthMiddleware(session_store: SessionStore, user_store: UserStore):
    async def middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        method = request.method.upper()
        path = request.url.path
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        record = session_store.get(session_id) if session_id else None
        if record is not None and user_store.get_by_id(record.user_id) is None:
            session_store.delete(session_id or "")
            record = None
        request.state.admin_user = record
        if is_public(method, path) or record is not None:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)

    return middleware
```

In `create_app` after `app = FastAPI(...)`:

```python
from apps.admin.auth_middleware import AdminAuthMiddleware
from apps.admin.passwords import hash_password, verify_password
from apps.admin.session_store import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, SessionStore
from apps.admin.user_rules import password_error, username_error
from apps.admin.user_store import UserAlreadyExists, build_user_store, public_user
```

```python
user_store = build_user_store(config_root)
session_store = SessionStore()
app.state.user_store = user_store
app.state.session_store = session_store
app.middleware("http")(AdminAuthMiddleware(session_store, user_store))
```

Add SPA route `GET /login` next to existing `admin_page` decorators.

Cookie helpers inside `create_app`:

```python
def _set_session_cookie(response: JSONResponse, session_id: str) -> JSONResponse:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )
    return response


def _clear_session_cookie(response: JSONResponse) -> JSONResponse:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


def _current_user(request: Request):
    return getattr(request.state, "admin_user", None)
```

Pydantic:

```python
class AdminAuthCredentialsRequest(BaseModel):
    username: str
    password: str
```

Need `from fastapi import Request` added to imports.

Auth handlers (inside `create_app`):

```python
@app.get("/api/auth/status")
def auth_status(request: Request) -> dict[str, Any]:
    record = _current_user(request)
    user = user_store.get_by_id(record.user_id) if record else None
    return {
        "authenticated": user is not None,
        "needs_bootstrap": user_store.count() == 0,
        "user": public_user(user) if user else None,
    }


@app.post("/api/auth/bootstrap")
def auth_bootstrap(req: AdminAuthCredentialsRequest) -> JSONResponse:
    err = username_error(req.username) or password_error(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if user_store.count() != 0:
        raise HTTPException(status_code=409, detail="已存在用户，请登录")
    try:
        user = user_store.create(req.username, hash_password(req.password))
    except UserAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    sid = session_store.create(user["id"], user["username"])
    body = JSONResponse({"ok": True, "user": public_user(user)})
    return _set_session_cookie(body, sid)


@app.post("/api/auth/login")
def auth_login(req: AdminAuthCredentialsRequest) -> JSONResponse:
    user = user_store.get_by_username(req.username)
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    sid = session_store.create(user["id"], user["username"])
    body = JSONResponse({"ok": True, "user": public_user(user)})
    return _set_session_cookie(body, sid)


@app.post("/api/auth/logout")
def auth_logout(request: Request) -> JSONResponse:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        session_store.delete(sid)
    return _clear_session_cookie(JSONResponse({"ok": True}))


@app.get("/api/auth/me")
def auth_me(request: Request) -> dict[str, Any]:
    record = _current_user(request)
    user = user_store.get_by_id(record.user_id) if record else None
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    return public_user(user)
```

Starlette `app.middleware("http")` must be registered **before** routes work; registering after route defs is OK in FastAPI if done before serving. Put the `app.middleware("http")(...)` call immediately after creating stores, still inside `create_app`, before or after routes — FastAPI allows adding middleware before first request. Add it right after assigning `app.state` so tests see it.

Existing tests: switch to `make_admin_client` / `bootstrap_client` so they stop 401ing.

- [ ] **Step 4: Run tests**

Run:

```
pytest tests/unit/apps/test_admin_auth.py tests/unit/apps/test_admin_main.py tests/unit/apps/test_admin_cron_jobs_api.py tests/unit/apps/test_admin_message_templates.py tests/unit/skill_system/test_skill_env_on_run.py -q
```

Expected: PASS, 0 failures.

If `test_admin_health_status_and_page` still expects unauthenticated `/admin` 200, update it as specified above.

- [ ] **Step 5: Commit** (skip unless asked)

```bash
git add apps/admin/auth_middleware.py apps/admin/main.py tests/support/admin_client.py tests/unit/apps/test_admin_auth.py tests/unit/apps/test_admin_main.py tests/unit/apps/test_admin_cron_jobs_api.py tests/unit/apps/test_admin_message_templates.py tests/unit/skill_system/test_skill_env_on_run.py
git commit -m "feat(admin): intercept Admin requests with session cookie"
```

---

### Task 6: User management and password-change APIs

**Files:**
- Modify: `apps/admin/main.py`
- Test: `tests/unit/apps/test_admin_auth.py`

**Interfaces:**
- Consumes: Task 5 `request.state.admin_user`, `user_store`, `session_store`
- Produces:
  - `GET /api/users` → `{items: public_user[], total}`
  - `POST /api/users` `{username, password}`
  - `DELETE /api/users/{user_id}`
  - `POST /api/users/me/password` `{old_password, new_password}`
- No username update route.

- [ ] **Step 1: Write failing tests**

```python
def test_users_crud_and_self_delete_returns_to_bootstrap(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password12"})
    created = client.post("/api/users", json={"username": "bob", "password": "password12"})
    assert created.status_code == 200
    bob_id = created.json()["user"]["id"]
    listed = client.get("/api/users")
    assert listed.status_code == 200
    assert {item["username"] for item in listed.json()["items"]} == {"admin", "bob"}
    assert all("password_hash" not in item for item in listed.json()["items"])
    assert client.delete(f"/api/users/{bob_id}").status_code == 200
    me = client.get("/api/auth/me").json()
    gone = client.delete(f"/api/users/{me['id']}")
    assert gone.status_code == 200
    status = client.get("/api/auth/status")
    assert status.json()["needs_bootstrap"] is True
    assert client.get("/api/users").status_code == 401


def test_change_password_requires_old_and_does_not_rename(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password12"})
    bad = client.post(
        "/api/users/me/password",
        json={"old_password": "nope-nope", "new_password": "password13"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "旧密码不正确"
    same = client.post(
        "/api/users/me/password",
        json={"old_password": "password12", "new_password": "password12"},
    )
    assert same.status_code == 400
    ok = client.post(
        "/api/users/me/password",
        json={"old_password": "password12", "new_password": "password13"},
    )
    assert ok.status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "admin"
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "admin", "password": "password13"}).status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/apps/test_admin_auth.py::test_users_crud_and_self_delete_returns_to_bootstrap -v`

Expected: FAIL 404 (route missing)

- [ ] **Step 3: Implement routes**

```python
class AdminUserCreateRequest(BaseModel):
    username: str
    password: str


class AdminPasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str
```

```python
@app.get("/api/users")
def list_users() -> dict[str, Any]:
    items = [public_user(item) for item in user_store.list_users()]
    return {"items": items, "total": len(items)}


@app.post("/api/users")
def create_user(req: AdminUserCreateRequest) -> dict[str, Any]:
    err = username_error(req.username) or password_error(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    try:
        user = user_store.create(req.username, hash_password(req.password))
    except UserAlreadyExists as exc:
        raise HTTPException(status_code=409, detail="用户名已存在") from exc
    return {"ok": True, "user": public_user(user)}


@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, request: Request) -> dict[str, Any]:
    existing = user_store.get_by_id(user_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user_store.delete(user_id)
    session_store.delete_by_user_id(user_id)
    return {"ok": True, "id": user_id}


@app.post("/api/users/me/password")
def change_my_password(req: AdminPasswordChangeRequest, request: Request) -> dict[str, Any]:
    err = password_error(req.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    record = _current_user(request)
    user = user_store.get_by_id(record.user_id) if record else None
    if user is None:
        raise HTTPException(status_code=401, detail="未登录")
    if not verify_password(req.old_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="旧密码不正确")
    if req.old_password == req.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    user_store.update_password_hash(user["id"], hash_password(req.new_password))
    return {"ok": True}
```

Add SPA decorator `GET /users` on `admin_page`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/apps/test_admin_auth.py tests/unit/apps/test_admin_user_store.py -q`

Expected: PASS

- [ ] **Step 5: Commit** (skip unless asked)

```bash
git add apps/admin/main.py tests/unit/apps/test_admin_auth.py
git commit -m "feat(admin): add user CRUD and self password change"
```

---

### Task 7: Admin Web login, users page, topbar

**Files:**
- Create: `apps/admin-web/src/LoginPage.tsx`
- Create: `apps/admin-web/src/UsersPage.tsx`
- Modify: `apps/admin-web/src/App.tsx`
- Modify: `apps/admin-web/src/App.css`

**Interfaces:**
- Consumes: `/api/auth/*`, `/api/users`
- Produces: `/login` full-screen card; `/users` table; topbar username with 修改密码 / 退出
- `api()` on 401 (except `/api/auth/login` and `/api/auth/bootstrap`) sets `window.location.href = '/login'`

- [ ] **Step 1: Update `api()` 401 handling**

Replace the `fetch` helper so 401 on non-auth-credential endpoints bounce to login:

```ts
const api = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  const text = await response.text()
  let data: { detail?: unknown } | null = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = null
    }
  }
  if (!response.ok) {
    const isAuthForm = url.startsWith('/api/auth/login') || url.startsWith('/api/auth/bootstrap')
    if (response.status === 401 && !isAuthForm) {
      if (window.location.pathname !== '/login') {
        const next = encodeURIComponent(window.location.pathname)
        window.location.href = `/login?next=${next}`
      }
    }
    const detail = data?.detail
    let message = text || response.statusText
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = detail
        .map((item) => {
          if (typeof item === 'string') return item
          if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg?: string }).msg)
          return JSON.stringify(item)
        })
        .join('; ')
    }
    throw new Error(message)
  }
  return (data ?? null) as T
}
```

There is no frontend unit test runner required. Treat “failing test” as: TypeScript must compile; do not add a new test framework.

- [ ] **Step 2: Add LoginPage**

Create `apps/admin-web/src/LoginPage.tsx` with Ant Design `Card` + `Form`:

- On mount `GET /api/auth/status`. If `authenticated`, `window.location.replace(safeNext || '/overview')`.
- If `needs_bootstrap`, fields: username, password, confirmPassword; submit `POST /api/auth/bootstrap`.
- Else fields: username, password; submit `POST /api/auth/login`.
- `safeNext`: read `next` query, allow only paths starting with `/` and not `//`.
- Button text: 「创建首个账号」 vs 「登录」.
- Show `Error` message inside the card.

- [ ] **Step 3: Add UsersPage**

Create `apps/admin-web/src/UsersPage.tsx`:

- Table columns: 用户名, 创建时间, 删除 (`Popconfirm`).
- Button 新建用户 → Modal username + password (`Input.Password`).
- After delete, reload list. If `GET /api/users` 401 or list empty after deleting self, browser is already redirected by `api()`.

- [ ] **Step 4: Wire App.tsx + CSS**

At the top of `function App()` (before data-loading effects):

```tsx
if (window.location.pathname === '/login') {
  return (
    <ConfigProvider theme={{ token: { colorPrimary: '#e85d75', borderRadius: 12 } }}>
      <LoginPage />
    </ConfigProvider>
  )
}
```

Add to `pathToView` / `viewToPath`:

```ts
'/users': 'users',
users: '/users',
```

Add `pageMeta.users = { title: '用户管理', desc: '创建与删除控制台账号；用户名创建后不可修改。' }`

Add menu item under 设置, after `advanced`:

```ts
{ key: 'users', icon: <UserOutlined />, label: '用户管理' },
```

Import `UserOutlined`, `LogoutOutlined`, `Dropdown`.

State: `currentUser` from `GET /api/auth/me` in a `useEffect`. Password modal: old / new / confirm → `POST /api/users/me/password`. Logout → `POST /api/auth/logout` then `window.location.href = '/login'`.

In the topbar (right of title), replace the lone Badge with:

```tsx
<Space>
  <Dropdown
    menu={{
      items: [
        { key: 'password', label: '修改密码' },
        { key: 'logout', label: '退出' },
      ],
      onClick: ({ key }) => {
        if (key === 'password') setPasswordModalOpen(true)
        if (key === 'logout') void logout()
      },
    }}
  >
    <Button type="text">{currentUser?.username || '账号'}</Button>
  </Dropdown>
  <Badge status="success" text="正常" />
</Space>
```

In `renderContent`, when `active === 'users'` render `<UsersPage />`.

`App.css`:

```css
.login-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--fn-bg-secondary);
}
.login-card {
  width: 420px;
}
```

- [ ] **Step 5: Typecheck / existing pytest still pass**

Run: `pytest tests/unit/apps/test_admin_auth.py tests/unit/apps/test_admin_main.py -q`

From `apps/admin-web`: `npx tsc -b --pretty false` if the project has it; otherwise skip if no tsc script.

Expected: pytest PASS.

- [ ] **Step 6: Commit** (skip unless asked)

```bash
git add apps/admin-web/src/LoginPage.tsx apps/admin-web/src/UsersPage.tsx apps/admin-web/src/App.tsx apps/admin-web/src/App.css
git commit -m "feat(admin-web): add login and user management UI"
```

---

### Task 8: Docs

**Files:**
- Create: `docs/releases/v1.2.0.md`
- Modify: `docs/business-logic/18-apps-api-admin-cli.md` (SPA table + new auth/users API subsection)
- Modify: `README.md` version badge `1.1.4` → `1.2.0` and “当前阶段” sentence
- Modify: spec status `待审阅` → `已确认（实现中）`

- [ ] **Step 1: Write release notes** covering: first-open bootstrap, cookie login, user management, bcrypt, in-memory session restart, existing MySQL volumes auto-create `users` via `CREATE TABLE IF NOT EXISTS`.

- [ ] **Step 2: Patch business-logic 18**

Add `/login` and `/users` to the SPA path list. New subsection 3.3.x:

| 方法 | 路径 | 说明 |
| GET | `/api/auth/status` | 公开；bootstrap / 登录态 |
| POST | `/api/auth/bootstrap` | 仅 `count==0` |
| POST | `/api/auth/login` | Cookie 会话 |
| POST | `/api/auth/logout` | 清 Cookie |
| GET | `/api/auth/me` | 当前用户 |
| GET/POST | `/api/users` | 列表 / 创建 |
| DELETE | `/api/users/{id}` | 可删自己与最后用户 |
| POST | `/api/users/me/password` | 改当前用户密码 |

Note middleware: unauthenticated `/api/*` → 401; pages → 302 `/login`.

- [ ] **Step 3: Run a focused regression**

Run: `pytest tests/unit/apps/test_admin_auth.py tests/unit/apps/test_admin_user_store.py tests/unit/apps/test_admin_main.py -q`

Expected: PASS

- [ ] **Step 4: Commit** (skip unless asked)

```bash
git add docs/releases/v1.2.0.md docs/business-logic/18-apps-api-admin-cli.md docs/superpowers/specs/2026-09-15-admin-login-user-management-design.md README.md
git commit -m "docs: record Admin login in v1.2.0"
```

---

## Self-review

**Spec coverage**

| Spec section | Task |
| --- | --- |
| Admin-only interceptor + Cookie | Task 5 |
| `users` table mysql/sqlite/memory | Task 3 |
| bcrypt, no plaintext | Task 1, 2, 6 |
| bootstrap when empty | Task 5, 7 |
| in-memory session, restart logs in again | Task 4, 5 |
| equal permissions, user CRUD | Task 6, 7 |
| change own password, never username | Task 6, 7 |
| delete self / last user → bootstrap | Task 6 |
| frontend login + users + topbar | Task 7 |
| existing Admin tests still work | Task 5 helper |
| v1.2.0 upgrade notes | Task 8 |

**Placeholder scan:** none remaining.

**Type consistency:** `SESSION_COOKIE_NAME`, `public_user`, `UserAlreadyExists`, `needs_bootstrap`, cookie TTL 12h match across tasks.
