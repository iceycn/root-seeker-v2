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
    assert password_error("a" * 8) is None
    assert password_error("a" * 73) is not None
    assert password_error("a" * 72) is None
    assert password_error("汉" * 25) is not None
    assert len("汉" * 25) >= 8
    assert len(("汉" * 25).encode("utf-8")) > 72


from apps.admin.user_store import MemoryUserStore, UserAlreadyExists, UsersAlreadyExist, public_user


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


def test_memory_create_first_only_when_empty() -> None:
    store = MemoryUserStore()
    first = store.create_first("admin", hash_password("password12"))
    assert first["username"] == "admin"
    try:
        store.create_first("other", hash_password("password12"))
        raise AssertionError("expected UsersAlreadyExist")
    except UsersAlreadyExist:
        pass
    assert store.count() == 1
    assert store.get_by_username("other") is None


def test_memory_store_update_password_keeps_username() -> None:
    store = MemoryUserStore()
    user = store.create("alice", hash_password("password12"))
    updated = store.update_password_hash(user["id"], hash_password("password13"))
    assert updated is not None
    assert updated["username"] == "alice"
    assert verify_password("password13", updated["password_hash"])


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


def test_sqlite_create_first_only_when_empty(tmp_path) -> None:
    store = SqliteUserStore(tmp_path / "users.sqlite")
    store.create_first("admin", hash_password("password12"))
    try:
        store.create_first("other", hash_password("password12"))
        raise AssertionError("expected UsersAlreadyExist")
    except UsersAlreadyExist:
        pass
    assert store.count() == 1
    assert store.get_by_username("other") is None


def test_build_user_store_follows_memory_backend(tmp_path) -> None:
    settings = RootSeekerSettings(storage_backend="memory")
    store = build_user_store(tmp_path, settings=settings)
    assert isinstance(store, MemoryUserStore)


def test_sqlite_store_username_case_sensitive(tmp_path) -> None:
    store = SqliteUserStore(tmp_path / "users.sqlite")
    bob = store.create("bob", hash_password("password12"))
    assert bob["username"] == "bob"
    bob_upper = store.create("Bob", hash_password("password12"))
    assert bob_upper["username"] == "Bob"
    assert store.count() == 2
    assert store.get_by_username("Bob")["id"] == bob_upper["id"]
    assert store.get_by_username("Bob")["username"] == "Bob"
    assert store.get_by_username("bob")["id"] == bob["id"]
