from __future__ import annotations

from apps.admin.error_history import FileErrorChatHistoryStore, SqliteErrorChatHistoryStore


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
