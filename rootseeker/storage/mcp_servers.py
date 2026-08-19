"""Persist external MCP server definitions for Admin."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from rootseeker.infra_core.settings import RootSeekerSettings

__all__ = [
    "ALLOWED_MCP_TRANSPORTS",
    "FileMcpServerStore",
    "build_mcp_server_store",
    "mask_mcp_server_for_api",
]

ALLOWED_MCP_TRANSPORTS = frozenset({"stdio"})
MCP_DISCOVERY_STATUSES = frozenset({"pending", "discovering", "ready", "failed"})


class McpServerStore(Protocol):
    def list_servers(self) -> list[dict[str, Any]]: ...

    def get_server(self, server_id: str) -> dict[str, Any] | None: ...

    def upsert_server(self, server: dict[str, Any]) -> dict[str, Any]: ...

    def delete_server(self, server_id: str) -> None: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def mask_mcp_server_for_api(server: dict[str, Any]) -> dict[str, Any]:
    payload = dict(server)
    env = payload.get("env")
    if isinstance(env, dict):
        masked_env: dict[str, str] = {}
        for key, value in env.items():
            text = str(value or "")
            masked_env[str(key)] = "******" if text else ""
        payload["env"] = masked_env
        payload["has_env"] = any(str(v or "") for v in env.values())
    else:
        payload["has_env"] = False
    tools = payload.get("tools")
    if isinstance(tools, list):
        payload["tools_count"] = len(tools)
        payload["tool_names"] = [
            str(item.get("name") or "").strip()
            for item in tools
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
    else:
        payload["tools_count"] = 0
        payload["tool_names"] = []
    return payload


def _validate_transport(transport: str) -> str:
    normalized = str(transport or "stdio").strip().lower()
    if normalized not in ALLOWED_MCP_TRANSPORTS:
        raise ValueError(f"unsupported transport: {transport}")
    return normalized


def _normalize_server_payload(
    server: dict[str, Any],
    *,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    server_id = str(server.get("server_id") or (existing or {}).get("server_id") or "").strip()
    if not server_id:
        server_id = str(uuid.uuid4())
    name = str(server.get("name") or (existing or {}).get("name") or server_id).strip()
    if not name:
        raise ValueError("name is required")
    transport = _validate_transport(
        str(server.get("transport") or (existing or {}).get("transport") or "stdio")
    )
    command = str(server.get("command") or (existing or {}).get("command") or "").strip()
    if transport == "stdio" and not command:
        raise ValueError("command is required for stdio transport")

    raw_args = server.get("args") if "args" in server else (existing or {}).get("args")
    args = list(raw_args) if isinstance(raw_args, list) else []

    env = server.get("env") if "env" in server else (existing or {}).get("env")
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise ValueError("env must be an object")
    env_map = {str(k): str(v) for k, v in env.items()}

    cwd = str(server.get("cwd") or (existing or {}).get("cwd") or "").strip()
    enabled = server.get("enabled") if "enabled" in server else (existing or {}).get("enabled", True)
    tools = server.get("tools") if "tools" in server else (existing or {}).get("tools")
    if tools is None:
        tools = []
    if not isinstance(tools, list):
        raise ValueError("tools must be an array")

    timeout_seconds = server.get("timeout_seconds") if "timeout_seconds" in server else (
        (existing or {}).get("timeout_seconds") or 120.0
    )

    now = _now_iso()
    created_at = str((existing or {}).get("created_at") or server.get("created_at") or now)
    last_sync_at = server.get("last_sync_at") if "last_sync_at" in server else (existing or {}).get(
        "last_sync_at"
    )
    last_error = str(server.get("last_error") or (existing or {}).get("last_error") or "")
    raw_status = server.get("discovery_status") if "discovery_status" in server else (
        (existing or {}).get("discovery_status")
    )
    discovery_status = str(raw_status or "").strip().lower()
    if not discovery_status:
        discovery_status = "ready" if tools else "pending"
    if discovery_status not in MCP_DISCOVERY_STATUSES:
        raise ValueError(f"unsupported discovery_status: {discovery_status}")

    return {
        "server_id": server_id,
        "name": name,
        "transport": transport,
        "command": command,
        "args": [str(item) for item in args],
        "env": env_map,
        "cwd": cwd,
        "enabled": bool(enabled),
        "tools": list(tools),
        "timeout_seconds": float(timeout_seconds or 120.0),
        "last_sync_at": last_sync_at,
        "last_error": last_error,
        "discovery_status": discovery_status,
        "created_at": created_at,
        "updated_at": now,
    }


class FileMcpServerStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"servers": []})

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"servers": []}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"servers": []}
        data.setdefault("servers", [])
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_servers(self) -> list[dict[str, Any]]:
        items = self._load().get("servers", [])
        return sorted(
            [dict(item) for item in items if isinstance(item, dict)],
            key=lambda item: str(item.get("name") or ""),
        )

    def get_server(self, server_id: str) -> dict[str, Any] | None:
        for item in self.list_servers():
            if item.get("server_id") == server_id:
                return dict(item)
        return None

    def upsert_server(self, server: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        items = list(data.get("servers", []))
        server_id = str(server.get("server_id") or "").strip()
        existing = next((item for item in items if item.get("server_id") == server_id), None) if server_id else None
        if existing is None:
            name = str(server.get("name") or "").strip()
            existing = next((item for item in items if item.get("name") == name), None)
        normalized = _normalize_server_payload(server, existing=existing)
        for other in items:
            if other.get("name") == normalized["name"] and other.get("server_id") != normalized["server_id"]:
                raise ValueError(f"MCP server name already exists: {normalized['name']}")
        items = [item for item in items if item.get("server_id") != normalized["server_id"]]
        items.append(normalized)
        data["servers"] = items
        self._save(data)
        return dict(normalized)

    def delete_server(self, server_id: str) -> None:
        data = self._load()
        data["servers"] = [item for item in data.get("servers", []) if item.get("server_id") != server_id]
        self._save(data)


def build_mcp_server_store(config_root: Path | str) -> FileMcpServerStore:
    settings = RootSeekerSettings()
    root = Path(config_root)
    path = root / "data" / "admin" / "mcp_servers.json"
    if settings.admin_config_path:
        admin_path = Path(settings.admin_config_path)
        if admin_path.is_absolute():
            path = admin_path.parent / "mcp_servers.json"
        else:
            path = root / admin_path.parent / "mcp_servers.json"
    return FileMcpServerStore(path)
