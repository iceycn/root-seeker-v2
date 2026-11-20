"""Detect whether a Kubernetes MCP server is already registered."""

from __future__ import annotations

from typing import Any

from rootseeker.contracts.tool import ToolScope
from rootseeker.k8s.config import K8sConfig
from rootseeker.mcp_plane.registry import ToolRegistry

__all__ = ["scan_k8s_mcp"]

_MARKERS = ("k8s", "kubernetes", "kubectl")


def scan_k8s_mcp(registry: ToolRegistry) -> dict[str, Any]:
    """Scan discovered external MCP tools for a Kubernetes protocol.

    Internal ``k8s.*`` tools are not a protocol. Only external MCP servers
    whose id, tool name, or tags mention Kubernetes count.
    """
    servers: dict[str, list[str]] = {}
    for spec in registry.list_specs():
        if spec.scope != ToolScope.EXTERNAL:
            continue
        blob = " ".join([spec.server_name, spec.name, *spec.tags]).lower()
        if not any(marker in blob for marker in _MARKERS):
            continue
        servers.setdefault(spec.server_name, []).append(spec.name)

    window = K8sConfig.from_env().log_window_minutes
    tools = sorted(name for names in servers.values() for name in names)
    present = bool(servers)
    if not present:
        summary = "未扫描到 Kubernetes MCP 协议，跳过读取。"
    else:
        summary = "已扫描到 Kubernetes MCP 协议。"
    return {
        "kind": "status",
        "mcp_present": present,
        "configured": present,
        # Absence is a completed scan, not a failed read. Callers stop on mcp_present.
        "ok": True,
        "summary": summary,
        "mcp_servers": sorted(servers),
        "mcp_tools": tools,
        "log_window_minutes": window,
        "log_window_seconds": window * 60,
        "items": [],
        "anomalies": [],
        "errors": [],
    }
