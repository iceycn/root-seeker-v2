"""Tests for notification channel store and backend resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.backend_resolve import resolve_notification_channel_store
from rootseeker.storage.notification_channels import (
    FileNotificationChannelStore,
    SqliteNotificationChannelStore,
    build_notification_channel_store,
    mask_channel_for_api,
    migrate_legacy_callbacks_from_admin,
)


def test_resolve_notification_channel_store_follows_storage_backend(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "mysql")
    assert resolve_notification_channel_store(RootSeekerSettings()) == "mysql"

    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "sqlite")
    assert resolve_notification_channel_store(RootSeekerSettings()) == "sqlite"

    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "memory")
    assert resolve_notification_channel_store(RootSeekerSettings()) == "file"


def test_file_notification_channel_store_crud(tmp_path: Path) -> None:
    store = FileNotificationChannelStore(tmp_path / "channels.json")
    saved = store.upsert_channel(
        {
            "name": "ops-feishu",
            "channel_type": "feishu",
            "endpoint_url": "https://example.com/feishu",
            "secret": "abc123",
            "enabled": True,
        }
    )
    assert saved["channel_id"]
    assert store.list_channels()[0]["name"] == "ops-feishu"

    masked = mask_channel_for_api(saved)
    assert masked["has_secret"] is True
    assert "secret" not in masked

    store.update_settings({"broadcast_enabled": False})
    assert store.get_settings()["broadcast_enabled"] is False

    store.delete_channel(saved["channel_id"])
    assert store.list_channels() == []


def test_sqlite_notification_channel_store_crud(tmp_path: Path) -> None:
    store = SqliteNotificationChannelStore(tmp_path / "channels.db")
    first = store.upsert_channel(
        {
            "name": "ding",
            "channel_type": "dingtalk",
            "endpoint_url": "https://example.com/ding",
        }
    )
    second = store.upsert_channel(
        {
            "name": "slack",
            "channel_type": "slack",
            "endpoint_url": "https://example.com/slack",
            "enabled": False,
        }
    )
    assert len(store.list_channels()) == 2
    assert store.get_channel(first["channel_id"]) is not None
    store.delete_channel(second["channel_id"])
    assert len(store.list_channels()) == 1


def test_build_notification_channel_store_memory_uses_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "memory")
    store = build_notification_channel_store(tmp_path)
    assert isinstance(store, FileNotificationChannelStore)


def test_migrate_legacy_callbacks_from_admin(tmp_path: Path) -> None:
    store = FileNotificationChannelStore(tmp_path / "channels.json")
    admin_data = {
        "callbacks": [
            {
                "name": "legacy-webhook",
                "channel": "webhook",
                "url": "https://example.com/hook",
                "enabled": True,
            }
        ]
    }
    migrated = migrate_legacy_callbacks_from_admin(admin_data, store)
    assert migrated["callbacks"] == []
    assert store.list_channels()[0]["name"] == "legacy-webhook"


def test_duplicate_channel_name_rejected(tmp_path: Path) -> None:
    store = FileNotificationChannelStore(tmp_path / "channels.json")
    store.upsert_channel(
        {
            "channel_id": "id-1",
            "name": "dup",
            "channel_type": "webhook",
            "endpoint_url": "https://example.com/one",
        }
    )
    with pytest.raises(ValueError, match="already exists"):
        store.upsert_channel(
            {
                "channel_id": "id-2",
                "name": "dup",
                "channel_type": "feishu",
                "endpoint_url": "https://example.com/two",
            }
        )
