"""Tests for Admin advanced-settings env injection into MCP stdio processes."""

from __future__ import annotations

import sys
from pathlib import Path

from rootseeker.mcp_plane.process_env import env_from_admin_items, merge_stdio_env
from rootseeker.mcp_plane.server_manager import discover_stdio_tools
from rootseeker.mcp_plane.stdio_session import McpStdioSession

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"


def test_env_from_admin_items_keeps_runtime_and_mcp_scopes() -> None:
    result = env_from_admin_items(
        [
            {"key": "SHARED_TOKEN", "value": "shared", "scope": "runtime"},
            {"key": "MCP_ONLY", "value": "mcp-secret", "scope": "mcp"},
            {"key": "SKILL_ONLY", "value": "skill-secret", "scope": "skill"},
            {"key": "", "value": "ignored"},
        ]
    )
    assert result == {"SHARED_TOKEN": "shared", "MCP_ONLY": "mcp-secret"}


def test_env_from_admin_items_defaults_missing_scope_to_runtime() -> None:
    result = env_from_admin_items([{"key": "FOO", "value": "bar"}])
    assert result == {"FOO": "bar"}


def test_merge_stdio_env_server_json_overrides_admin() -> None:
    merged = merge_stdio_env(
        extra_env={"TOKEN": "from-admin", "KEEP": "admin"},
        server_env={"TOKEN": "from-server"},
    )
    assert merged == {"TOKEN": "from-server", "KEEP": "admin"}


def test_stdio_session_sees_injected_env() -> None:
    session = McpStdioSession(
        sys.executable,
        [str(FIXTURE)],
        env={"MCP_TEST_KEY": "from-advanced-settings"},
    )
    try:
        result = session.call_tool("echo_env", {"key": "MCP_TEST_KEY"})
        assert result["ok"] is True
        assert result["text"] == "from-advanced-settings"
    finally:
        session.close()


def test_stdio_session_server_env_overrides_admin_extra_env() -> None:
    env = merge_stdio_env(
        extra_env={"MCP_TEST_KEY": "from-admin"},
        server_env={"MCP_TEST_KEY": "from-server"},
    )
    session = McpStdioSession(sys.executable, [str(FIXTURE)], env=env)
    try:
        result = session.call_tool("echo_env", {"key": "MCP_TEST_KEY"})
        assert result["ok"] is True
        assert result["text"] == "from-server"
    finally:
        session.close()


def test_discover_stdio_tools_lists_echo_env() -> None:
    tools = discover_stdio_tools(
        {
            "command": sys.executable,
            "args": [str(FIXTURE)],
            "timeout_seconds": 30.0,
        },
        extra_env={"MCP_DISCOVER_KEY": "discover-ok"},
    )
    names = {tool.get("name") for tool in tools}
    assert "echo_env" in names
