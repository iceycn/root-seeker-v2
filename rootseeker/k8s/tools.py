"""MCP tool bindings for Kubernetes anomaly evidence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp_servers.internal.tool_schemas import parameter_schema_for
from rootseeker.contracts.tool import ToolScope, ToolSpec
from rootseeker.k8s.mcp_scan import scan_k8s_mcp
from rootseeker.k8s.reader import K8sQuery, KubernetesReader
from rootseeker.mcp_plane.registry import ToolRegistry

__all__ = ["build_k8s_tools"]

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


def build_k8s_tools(
    registry: ToolRegistry,
    reader: KubernetesReader | None = None,
) -> list[tuple[ToolSpec, ToolHandler]]:
    active = reader or KubernetesReader.from_env()
    server = "internal"
    scope = ToolScope.INTERNAL

    def _query(args: dict[str, Any]) -> K8sQuery:
        return K8sQuery.from_args(args if isinstance(args, dict) else {})

    def _without_protocol(kind: str) -> dict[str, Any]:
        blocked = scan_k8s_mcp(registry)
        blocked["kind"] = kind
        return blocked

    def _read(kind: str, args: dict[str, Any], fn: ToolHandler) -> dict[str, Any]:
        scan = scan_k8s_mcp(registry)
        if not scan["mcp_present"]:
            blocked = dict(scan)
            blocked["kind"] = kind
            return blocked
        result = fn(args)
        result["mcp_present"] = True
        result["mcp_servers"] = scan["mcp_servers"]
        result["mcp_tools"] = scan["mcp_tools"]
        return result

    bindings: list[tuple[str, str, ToolHandler]] = [
        (
            "k8s.status",
            "扫描已注册的外部 MCP，判断有没有 Kubernetes 协议。没有则不要读取 CPU、内存、磁盘和日志",
            lambda _args: _without_protocol("status"),
        ),
        (
            "k8s.read_cpu",
            "读取 Pod CPU 用量，并对照 limit 标出使用率，供异常分析使用",
            lambda args: _read("cpu", args, lambda raw: active.read_cpu(_query(raw))),
        ),
        (
            "k8s.read_memory",
            "读取 Pod 内存用量，并对照 limit 标出使用率，供异常分析使用",
            lambda args: _read("memory", args, lambda raw: active.read_memory(_query(raw))),
        ),
        (
            "k8s.read_disk",
            "读取节点文件系统、Pod 临时存储和卷的磁盘用量，供异常分析使用",
            lambda args: _read("disk", args, lambda raw: active.read_disk(_query(raw))),
        ),
        (
            "k8s.read_logs",
            "读取 Pod 最近一段时间的容器日志。窗口默认 ROOTSEEKER_K8S_LOG_WINDOW_MINUTES=5 分钟",
            lambda args: _read("logs", args, lambda raw: active.read_logs(_query(raw))),
        ),
        (
            "k8s.collect_snapshot",
            "一次读取 CPU、内存、磁盘和日志窗口，作为异常分析的 Kubernetes 证据",
            lambda args: _read("snapshot", args, lambda raw: active.collect_snapshot(_query(raw))),
        ),
    ]
    tools: list[tuple[ToolSpec, ToolHandler]] = []
    for name, description, handler in bindings:
        tools.append(
            (
                ToolSpec(
                    name=name,
                    description=description,
                    server_name=server,
                    scope=scope,
                    tags=["k8s", "analysis"],
                    parameters_schema=parameter_schema_for(name),
                ),
                handler,
            )
        )
    return tools
