from __future__ import annotations

from apps.admin.error_history import (
    FileErrorChatHistoryStore,
    MysqlErrorChatHistoryStore,
    SqliteErrorChatHistoryStore,
    sort_error_history_items,
)


def test_file_error_history_store_roundtrip(tmp_path) -> None:
    store = FileErrorChatHistoryStore(tmp_path / "history.json")
    item = store.append({"content": "boom", "case": {"case_id": "c1"}})

    assert item["id"]
    assert store.list_items()[0]["content"] == "boom"

    store.clear()
    assert store.list_items() == []


def test_sqlite_error_history_store_roundtrip(tmp_path) -> None:
    store = SqliteErrorChatHistoryStore(tmp_path / "history.db")
    item = store.append({"content": "boom", "case": {"case_id": "c1"}})

    assert item["id"]
    assert store.list_items()[0]["case"]["case_id"] == "c1"

    store.clear()
    assert store.list_items() == []


def test_sort_error_history_items_by_created_at() -> None:
    items = [
        {"id": "b", "created_at": "2026-09-03T07:30:00+00:00"},
        {"id": "a", "created_at": "2026-09-03T07:20:00+00:00"},
        {"id": "c", "created_at": "2026-09-03T07:40:00+00:00"},
    ]
    assert [item["id"] for item in sort_error_history_items(items)] == ["a", "b", "c"]


def test_mysql_history_list_sql_does_not_sort_payload() -> None:
    assert "ORDER BY" not in MysqlErrorChatHistoryStore.LIST_SQL.upper()
