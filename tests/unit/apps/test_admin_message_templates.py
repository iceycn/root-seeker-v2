"""Admin API tests for message templates."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.admin.main import create_app


def test_message_templates_crud_and_system_guard(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))

    listed = client.get("/api/message-templates")
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] >= 1
    assert any(item["template_id"] == "system-default" for item in payload["items"])
    assert any(v["name"] == "case_id" for v in payload["variables"])

    created = client.post(
        "/api/message-templates",
        json={"name": "简短", "body": "Case：{{case_id}}", "description": "d"},
    )
    assert created.status_code == 200
    template_id = created.json()["template"]["template_id"]

    updated = client.put(
        f"/api/message-templates/{template_id}",
        json={"body": "ID={{case_id}}"},
    )
    assert updated.status_code == 200
    assert updated.json()["template"]["body"] == "ID={{case_id}}"

    forbidden = client.delete("/api/message-templates/system-default")
    assert forbidden.status_code == 400

    deleted = client.delete(f"/api/message-templates/{template_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/message-templates/{template_id}").status_code == 404


def test_notification_channel_template_id_roundtrip(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    templates = client.get("/api/message-templates").json()["items"]
    system_id = next(item["template_id"] for item in templates if item["kind"] == "system")

    created = client.post(
        "/api/notification-channels",
        json={
            "name": "ops",
            "channel_type": "webhook",
            "endpoint_url": "https://example.com/hook",
            "template_id": system_id,
        },
    )
    assert created.status_code == 200
    channel = created.json()["channel"]
    assert channel["template_id"] == system_id

    channel_id = channel["channel_id"]
    updated = client.put(
        f"/api/notification-channels/{channel_id}",
        json={"template_id": ""},
    )
    assert updated.status_code == 200
    assert updated.json()["channel"]["template_id"] == ""
