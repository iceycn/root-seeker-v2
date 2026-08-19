"""Tests for external MCP server registration via stdio."""

from __future__ import annotations

import sys
from pathlib import Path

from rootseeker.contracts.tool import ToolCallRequest, ToolScope
from rootseeker.mcp_plane import (
    McpExternalClient,
    McpGateway,
    McpServerManager,
    PolicyGuard,
    ToolRegistry,
)
from rootseeker.mcp_plane.server_manager import (
    build_external_tool_name,
    discover_stdio_tools,
    register_mcp_servers_from_store,
)
from rootseeker.observability.audit import InMemoryAuditLog
from rootseeker.storage.mcp_servers import FileMcpServerStore

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"


class _MemoryMcpStore:
    def __init__(self, servers: list[dict]) -> None:
        self._servers = list(servers)

    def list_servers(self) -> list[dict]:
        return list(self._servers)


def test_register_stdio_mcp_server_and_invoke_via_gateway(tmp_path: Path) -> None:
    tools = discover_stdio_tools(
        {
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "timeout_seconds": 30.0,
        }
    )
    store = FileMcpServerStore(tmp_path / "mcp_servers.json")
    saved = store.upsert_server(
        {
            "name": "echo-fixture",
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "enabled": True,
            "tools": tools,
            "discovery_status": "ready",
        }
    )
    server_id = saved["server_id"]

    registry = ToolRegistry()
    external_client = McpExternalClient()
    manager = McpServerManager()
    results = register_mcp_servers_from_store(store, registry, external_client, manager=manager)
    assert results[0]["ok"] is True

    registered_name = build_external_tool_name(server_id, "echo")
    spec = registry.get_spec(registered_name)
    assert spec is not None
    assert spec.scope == ToolScope.EXTERNAL
    assert spec.server_name == server_id

    gateway = McpGateway(registry, PolicyGuard(), InMemoryAuditLog(), external_client=external_client)
    result = gateway.invoke(
        ToolCallRequest(
            case_id="case-mcp",
            step_id="step-mcp",
            skill_name="tests/mcp",
            tool_name=registered_name,
            arguments={"message": "gateway-echo"},
        ),
        actor="unit-test",
        plugin_id="test.mcp",
    )
    assert result.ok is True
    assert result.content["text"] == "gateway-echo"

    manager._close_all_sessions()


def test_mcp_stdio_invoke_uses_admin_extra_env() -> None:
    tools = discover_stdio_tools(
        {
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "timeout_seconds": 30.0,
        },
        extra_env={"MCP_TEST_KEY": "from-admin"},
    )
    store = _MemoryMcpStore(
        [
            {
                "server_id": "echo-env",
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(FIXTURE)],
                "enabled": True,
                "tools": tools,
                "discovery_status": "ready",
            }
        ]
    )
    registry = ToolRegistry()
    external_client = McpExternalClient()
    manager = McpServerManager(extra_env={"MCP_TEST_KEY": "from-admin"})
    register_mcp_servers_from_store(store, registry, external_client, manager=manager)
    result = manager.invoke("echo-env", "ext.echo-env.echo_env", {"key": "MCP_TEST_KEY"})
    assert result["text"] == "from-admin"
    manager._close_all_sessions()


def test_mcp_extra_env_provider_restarts_session_on_change() -> None:
    env_box = {"MCP_TEST_KEY": "first"}
    tools = discover_stdio_tools(
        {
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "timeout_seconds": 30.0,
        },
        extra_env=env_box,
    )
    store = _MemoryMcpStore(
        [
            {
                "server_id": "echo-env",
                "transport": "stdio",
                "command": sys.executable,
                "args": [str(FIXTURE)],
                "enabled": True,
                "tools": tools,
                "discovery_status": "ready",
            }
        ]
    )
    registry = ToolRegistry()
    external_client = McpExternalClient()
    manager = McpServerManager(
        extra_env=dict(env_box),
        extra_env_provider=lambda: dict(env_box),
    )
    register_mcp_servers_from_store(store, registry, external_client, manager=manager)
    first = manager.invoke("echo-env", "ext.echo-env.echo_env", {"key": "MCP_TEST_KEY"})
    assert first["text"] == "first"
    env_box["MCP_TEST_KEY"] = "second"
    second = manager.invoke("echo-env", "ext.echo-env.echo_env", {"key": "MCP_TEST_KEY"})
    assert second["text"] == "second"
    manager._close_all_sessions()


def test_run_env_overlay_survives_provider_refresh_and_skill_key_wins() -> None:
    manager = McpServerManager(extra_env_provider=lambda: {"RUNTIME": "a"})
    manager.set_run_env_overlay({"SKILL_KEY": "secret", "RUNTIME": "from-skill"})
    env = manager.extra_env
    assert env["RUNTIME"] == "from-skill"
    assert env["SKILL_KEY"] == "secret"
    manager.set_run_env_overlay(None)
    cleared = manager.extra_env
    assert cleared == {"RUNTIME": "a"}
    assert "SKILL_KEY" not in cleared
