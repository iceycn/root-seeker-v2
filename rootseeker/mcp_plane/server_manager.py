"""Register and invoke external MCP servers configured via Admin."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

from rootseeker.contracts.tool import ToolPermissionLevel, ToolScope, ToolSpec
from rootseeker.mcp_plane.external_client import McpExternalClient
from rootseeker.mcp_plane.process_env import merge_stdio_env
from rootseeker.mcp_plane.registry import ToolRegistry
from rootseeker.mcp_plane.stdio_session import McpStdioSession

__all__ = [
    "McpServerManager",
    "build_external_tool_name",
    "discover_stdio_tools",
    "register_mcp_servers_from_store",
]


class McpServerStore(Protocol):
    def list_servers(self) -> list[dict[str, Any]]: ...


def build_external_tool_name(server_id: str, mcp_tool_name: str) -> str:
    return f"ext.{server_id}.{mcp_tool_name}"


def discover_stdio_tools(
    server: dict[str, Any],
    *,
    extra_env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    session = _build_stdio_session(server, extra_env=extra_env)
    try:
        session.connect()
        return session.list_tools()
    finally:
        session.close()


def register_mcp_servers_from_store(
    store: McpServerStore,
    registry: ToolRegistry,
    external_client: McpExternalClient,
    *,
    manager: McpServerManager | None = None,
) -> list[dict[str, Any]]:
    active_manager = manager or McpServerManager()
    return active_manager.reload_from_store(store, registry, external_client)


def _build_stdio_session(
    server: dict[str, Any],
    *,
    extra_env: dict[str, str] | None = None,
) -> McpStdioSession:
    command = str(server.get("command") or "").strip()
    raw_args = server.get("args")
    args = list(raw_args) if isinstance(raw_args, list) else []
    if command.lower() == "npx" and "-y" not in args and "--yes" not in args:
        args = ["-y", *[str(a) for a in args]]
    env = server.get("env")
    server_env = {str(k): str(v) for k, v in env.items()} if isinstance(env, dict) else {}
    env_map = merge_stdio_env(extra_env=extra_env, server_env=server_env)
    cwd = str(server.get("cwd") or "").strip() or None
    timeout = float(server.get("timeout_seconds") or 120.0)
    return McpStdioSession(command, [str(a) for a in args], env=env_map, cwd=cwd, timeout_seconds=timeout)


def _tool_permission_from_schema(input_schema: dict[str, Any] | None) -> ToolPermissionLevel:
    if not isinstance(input_schema, dict):
        return ToolPermissionLevel.READ
    return ToolPermissionLevel.READ


def _parameters_schema(tool: dict[str, Any]) -> dict[str, Any]:
    schema = tool.get("inputSchema")
    if isinstance(schema, dict):
        return dict(schema)
    return {"type": "object", "properties": {}}


class McpServerManager:
    """Keeps stdio sessions and routes external tool invocations to MCP servers."""

    def __init__(
        self,
        extra_env: dict[str, str] | None = None,
        extra_env_provider: Callable[[], dict[str, str]] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, McpStdioSession] = {}
        self._servers: dict[str, dict[str, Any]] = {}
        self._registered_tool_names: dict[str, str] = {}
        self._extra_env: dict[str, str] = dict(extra_env or {})
        self._extra_env_provider = extra_env_provider
        self._run_env_overlay: dict[str, str] = {}

    @property
    def extra_env(self) -> dict[str, str]:
        with self._lock:
            return self._refresh_extra_env_locked()

    @property
    def extra_env_provider(self) -> Callable[[], dict[str, str]] | None:
        return self._extra_env_provider

    def set_extra_env(self, extra_env: dict[str, str] | None) -> None:
        with self._lock:
            self._extra_env = dict(extra_env or {})
            self._close_all_sessions()

    def set_extra_env_provider(self, provider: Callable[[], dict[str, str]] | None) -> None:
        with self._lock:
            self._extra_env_provider = provider

    def set_run_env_overlay(self, overlay: dict[str, str] | None) -> None:
        with self._lock:
            self._run_env_overlay = dict(overlay or {})
            self._close_all_sessions()

    def _refresh_extra_env_locked(self) -> dict[str, str]:
        overlay = dict(self._run_env_overlay)
        if self._extra_env_provider is None:
            base = dict(self._extra_env)
        else:
            try:
                loaded = self._extra_env_provider()
            except Exception:
                base = dict(self._extra_env)
            else:
                base = dict(loaded or {})
                if base != self._extra_env:
                    self._extra_env = base
                    self._close_all_sessions()
        return {**base, **overlay}

    def reload_from_store(
        self,
        store: McpServerStore,
        registry: ToolRegistry,
        external_client: McpExternalClient,
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._close_all_sessions()
            self._servers.clear()
            self._registered_tool_names.clear()
            results: list[dict[str, Any]] = []
            for server in store.list_servers():
                server_id = str(server.get("server_id") or "").strip()
                if not server_id:
                    continue
                if not bool(server.get("enabled", True)):
                    results.append({"server_id": server_id, "ok": True, "skipped": True})
                    continue
                status = str(server.get("discovery_status") or "ready").strip().lower()
                if status == "discovering":
                    results.append({"server_id": server_id, "ok": True, "skipped": True, "reason": "discovering"})
                    continue
                if status == "failed":
                    results.append(
                        {
                            "server_id": server_id,
                            "ok": False,
                            "error": str(server.get("last_error") or "discovery failed"),
                        }
                    )
                    continue
                tools = server.get("tools")
                if status != "ready" or not isinstance(tools, list) or not tools:
                    results.append(
                        {
                            "server_id": server_id,
                            "ok": True,
                            "skipped": True,
                            "reason": status if status != "ready" else "no_tools",
                        }
                    )
                    continue
                try:
                    self._register_server(server, registry, external_client)
                    results.append(
                        {
                            "server_id": server_id,
                            "ok": True,
                            "tools": len(server.get("tools") or []),
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "server_id": server_id,
                            "ok": False,
                            "error": str(exc),
                        }
                    )
            return results

    def invoke(self, server_id: str, registered_tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            extra_env = self._refresh_extra_env_locked()
            server = self._servers.get(server_id)
            if server is None:
                raise RuntimeError(f"MCP server not loaded: {server_id}")
            mcp_tool_name = self._registered_tool_names.get(registered_tool_name, registered_tool_name)
            transport = str(server.get("transport") or "stdio").strip().lower()
            if transport != "stdio":
                raise RuntimeError(f"unsupported MCP transport: {transport}")
            session = self._sessions.get(server_id)
            if session is None:
                session = _build_stdio_session(server, extra_env=extra_env)
                session.connect()
                self._sessions[server_id] = session
            return session.call_tool(mcp_tool_name, arguments)

    def test_server(self, server: dict[str, Any]) -> dict[str, Any]:
        extra_env = self.extra_env
        transport = str(server.get("transport") or "stdio").strip().lower()
        if transport != "stdio":
            raise ValueError(f"unsupported transport: {transport}")
        session = _build_stdio_session(server, extra_env=extra_env)
        try:
            session.connect()
            tools = session.list_tools()
            probe: dict[str, Any] = {"tools_count": len(tools)}
            echo_tool = next((t for t in tools if t.get("name") == "echo"), None)
            if echo_tool is not None:
                probe["echo"] = session.call_tool("echo", {"message": "ping"})
            return {"ok": True, "tools": tools, "probe": probe}
        finally:
            session.close()

    def _register_server(
        self,
        server: dict[str, Any],
        registry: ToolRegistry,
        external_client: McpExternalClient,
    ) -> None:
        server_id = str(server.get("server_id") or "").strip()
        if not server_id:
            raise ValueError("server_id is required")
        transport = str(server.get("transport") or "stdio").strip().lower()
        if transport != "stdio":
            raise ValueError(f"unsupported transport: {transport}")

        tools = server.get("tools")
        if not isinstance(tools, list) or not tools:
            raise ValueError(f"MCP server has no discovered tools: {server_id}")

        registry.unregister_by_server(server_id)
        self._sessions.pop(server_id, None)

        session = _build_stdio_session(server, extra_env=self._refresh_extra_env_locked())
        session.connect()
        self._sessions[server_id] = session
        self._servers[server_id] = dict(server)

        for tool in tools:
            if not isinstance(tool, dict):
                continue
            mcp_tool_name = str(tool.get("name") or "").strip()
            if not mcp_tool_name:
                continue
            registered_name = build_external_tool_name(server_id, mcp_tool_name)
            spec = ToolSpec(
                name=registered_name,
                description=str(tool.get("description") or ""),
                permission_level=_tool_permission_from_schema(tool.get("inputSchema")),
                scope=ToolScope.EXTERNAL,
                parameters_schema=_parameters_schema(tool),
                server_name=server_id,
                tags=["external", "mcp", f"mcp-server:{server_id}"],
            )
            registry.register_external(spec)
            self._registered_tool_names[registered_name] = mcp_tool_name

        server_id_copy = server_id
        external_client.register_server(
            server_id,
            lambda tool_name, args: self.invoke(server_id_copy, tool_name, args),
        )

    def _close_all_sessions(self) -> None:
        for session in self._sessions.values():
            session.close()
        self._sessions.clear()
