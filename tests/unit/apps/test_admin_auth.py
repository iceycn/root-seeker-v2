from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from apps.admin.main import create_app
from apps.admin.passwords import hash_password
from apps.admin.session_store import SESSION_COOKIE_NAME, SESSION_TTL_SECONDS, SessionStore


def test_session_roundtrip_and_delete() -> None:
    assert SESSION_TTL_SECONDS == 12 * 3600
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
    home = client.get("/")
    assert home.status_code == 302
    assert "/login" in home.headers["location"]


def test_bootstrap_sets_cookie_then_second_bootstrap_conflicts(tmp_path) -> None:
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    first = client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password12"})
    assert first.status_code == 200
    assert SESSION_COOKIE_NAME in first.cookies
    second = client.post("/api/auth/bootstrap", json={"username": "other", "password": "password12"})
    assert second.status_code == 409
    assert second.json()["detail"] == "已存在用户，请登录"
    listed = client.get("/api/users")
    assert listed.status_code == 200
    assert [item["username"] for item in listed.json()["items"]] == ["admin"]


def test_bootstrap_rejected_when_user_already_in_store(tmp_path) -> None:
    app = create_app(tmp_path)
    app.state.user_store.create("alice", hash_password("password12"))
    client = TestClient(app, follow_redirects=False)
    resp = client.post("/api/auth/bootstrap", json={"username": "admin", "password": "password12"})
    assert resp.status_code == 409
    assert resp.json()["detail"] == "已存在用户，请登录"
    assert app.state.user_store.count() == 1
    assert app.state.user_store.get_by_username("admin") is None


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
    home = client.get("/")
    assert home.status_code == 200


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

