"""Tests for stdio MCP session client."""

from __future__ import annotations

import sys
from pathlib import Path

from rootseeker.mcp_plane.stdio_session import McpStdioSession

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "mcp_echo_server.py"


def test_stdio_session_lists_and_calls_echo_tool() -> None:
    session = McpStdioSession(sys.executable, [str(FIXTURE)])
    try:
        tools = session.list_tools()
        names = {tool.get("name") for tool in tools}
        assert "echo" in names
        result = session.call_tool("echo", {"message": "hello-mcp"})
        assert result["ok"] is True
        assert result["text"] == "hello-mcp"
    finally:
        session.close()
