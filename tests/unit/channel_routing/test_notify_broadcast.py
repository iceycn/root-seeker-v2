"""Tests for broadcast notification dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from rootseeker.channel_routing.notify_config import list_enabled_outbound_targets
from rootseeker.channel_routing.notify_dispatch import dispatch_broadcast_notify
from rootseeker.storage.notification_channels import FileNotificationChannelStore


@pytest.fixture
def channel_file(tmp_path: Path) -> Path:
    return tmp_path / "notification_channels.json"


def test_list_enabled_outbound_targets_skips_disabled(channel_file: Path) -> None:
    store = FileNotificationChannelStore(channel_file)
    store.upsert_channel(
        {
            "name": "enabled",
            "channel_type": "feishu",
            "endpoint_url": "https://example.com/enabled",
            "enabled": True,
        }
    )
    store.upsert_channel(
        {
            "name": "disabled",
            "channel_type": "slack",
            "endpoint_url": "https://example.com/disabled",
            "enabled": False,
        }
    )
    targets = list_enabled_outbound_targets(store)
    assert len(targets) == 1
    assert targets[0].channel == "feishu"
    assert targets[0].team == "default"


def test_dispatch_broadcast_notify_fan_out(channel_file: Path, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "memory")
    monkeypatch.setenv("ROOTSEEKER_NOTIFICATION_CHANNEL_FILE", str(channel_file))

    store = FileNotificationChannelStore(channel_file)
    store.upsert_channel(
        {
            "name": "a",
            "channel_type": "webhook",
            "endpoint_url": "https://example.com/a",
        }
    )
    store.upsert_channel(
        {
            "name": "b",
            "channel_type": "feishu",
            "endpoint_url": "https://example.com/b",
        }
    )

    with patch(
        "rootseeker.channel_routing.notify_dispatch.send_outbound_notification",
        side_effect=lambda target, message, registry=None: {
            "ok": True,
            "channel": target.channel,
            "message": message,
        },
    ) as send_mock:
        result = dispatch_broadcast_notify("hello", repo_root=tmp_path)

    assert result["ok"] is True
    assert result["sent"] == 2
    assert result["metadata"]["broadcast"] is True
    assert send_mock.call_count == 2


def test_dispatch_broadcast_notify_skips_when_no_enabled_channels(
    channel_file: Path,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "memory")
    monkeypatch.setenv("ROOTSEEKER_NOTIFICATION_CHANNEL_FILE", str(channel_file))
    FileNotificationChannelStore(channel_file)

    result = dispatch_broadcast_notify("hello", repo_root=tmp_path)
    assert result["ok"] is True
    assert result["metadata"]["skipped"] is True


def test_dispatch_broadcast_notify_legacy_when_disabled(
    channel_file: Path,
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ROOTSEEKER_STORAGE_BACKEND", "memory")
    monkeypatch.setenv("ROOTSEEKER_NOTIFICATION_CHANNEL_FILE", str(channel_file))
    store = FileNotificationChannelStore(channel_file)
    store.update_settings({"broadcast_enabled": False})

    with patch(
        "rootseeker.channel_routing.notify_dispatch.dispatch_env_resolved_notify",
        return_value={"ok": True, "channel": "webhook"},
    ) as legacy_mock:
        result = dispatch_broadcast_notify("hello", channel="webhook", repo_root=tmp_path)

    assert result["ok"] is True
    legacy_mock.assert_called_once_with("webhook", "hello")
