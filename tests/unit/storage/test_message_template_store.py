"""Tests for message template store."""

from __future__ import annotations

from pathlib import Path

import pytest

from rootseeker.storage.message_templates import FileMessageTemplateStore, SqliteMessageTemplateStore


def test_store_ensures_system_template(tmp_path: Path) -> None:
    store = FileMessageTemplateStore(tmp_path / "t.json")
    items = store.list_templates()
    assert any(t["template_id"] == "system-default" and t["kind"] == "system" for t in items)


def test_cannot_delete_system_template(tmp_path: Path) -> None:
    store = FileMessageTemplateStore(tmp_path / "t.json")
    with pytest.raises(ValueError, match="system"):
        store.delete_template("system-default")


def test_custom_template_crud(tmp_path: Path) -> None:
    store = FileMessageTemplateStore(tmp_path / "t.json")
    saved = store.upsert_template({"name": "简短", "body": "Case：{{case_id}}", "kind": "custom"})
    assert saved["kind"] == "custom"
    store.delete_template(saved["template_id"])
    assert store.get_template(saved["template_id"]) is None
    assert store.get_template("system-default") is not None


def test_sqlite_message_template_store_crud(tmp_path: Path) -> None:
    store = SqliteMessageTemplateStore(tmp_path / "t.db")
    assert store.get_template("system-default") is not None
    saved = store.upsert_template({"name": "custom-a", "body": "{{headline}}"})
    assert len(store.list_templates()) == 2
    store.delete_template(saved["template_id"])
    assert len(store.list_templates()) == 1
