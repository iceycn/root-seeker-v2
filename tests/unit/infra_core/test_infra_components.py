from pathlib import Path

import pytest

from rootseeker.infra_core import (
    AtomicJsonStore,
    EventBus,
    ExecApprovalGuard,
    NetworkGuard,
    PresenceRegistry,
    SafePathGuard,
)


def test_safe_path_guard_blocks_escape(tmp_path: Path) -> None:
    guard = SafePathGuard(tmp_path)
    inside = guard.ensure_safe(tmp_path / "a" / "b.json")
    assert str(inside).startswith(str(tmp_path))
    with pytest.raises(ValueError):
        guard.ensure_safe(tmp_path / ".." / "x.json")


def test_atomic_json_store_read_write(tmp_path: Path) -> None:
    store = AtomicJsonStore(tmp_path)
    target = tmp_path / "data" / "state.json"
    store.write(target, {"k": "v"})
    assert store.read(target) == {"k": "v"}


def test_network_guard_blocks_private_ip() -> None:
    guard = NetworkGuard()
    guard.validate_url("https://example.com")
    with pytest.raises(ValueError):
        guard.validate_url("http://127.0.0.1:8080/a")


def test_exec_approval_allowlist() -> None:
    guard = ExecApprovalGuard(allow_patterns=["echo ", "python "])
    assert guard.check("echo hi").approved is True
    assert guard.check("rm -rf /").approved is False


def test_event_bus_and_presence_registry() -> None:
    bus = EventBus()
    captured: list[dict] = []
    bus.subscribe("agent.lifecycle", lambda payload: captured.append(payload))
    bus.publish("agent.lifecycle", {"state": "running"})
    assert captured[0]["state"] == "running"

    presence = PresenceRegistry()
    presence.heartbeat(node_id="worker-1", role="worker", metadata={"zone": "z1"})
    nodes = presence.list_nodes()
    assert len(nodes) == 1
    assert nodes[0].role == "worker"
