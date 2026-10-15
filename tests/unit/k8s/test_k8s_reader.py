"""Kubernetes runtime reader used by anomaly analysis."""

from __future__ import annotations

import httpx

from mcp_servers.internal.handlers import register_internal_tools
from rootseeker.contracts.tool import ToolCallRequest, ToolScope, ToolSpec
from rootseeker.k8s.config import K8sConfig
from rootseeker.k8s.quantities import parse_bytes, parse_cpu_cores
from rootseeker.k8s.reader import K8sQuery, KubernetesReader
from rootseeker.k8s.tools import build_k8s_tools
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog
from tests.support.stub_internal_adapter import StubInternalToolAdapter


def test_quantity_parsers() -> None:
    assert parse_cpu_cores("200m") == 0.2
    assert parse_cpu_cores("1") == 1.0
    assert parse_bytes("100Mi") == 100 * 1024**2
    assert parse_bytes("1Ki") == 1024


def test_log_window_defaults_to_five_minutes(monkeypatch) -> None:
    monkeypatch.delenv("ROOTSEEKER_K8S_ENABLED", raising=False)
    monkeypatch.delenv("ROOTSEEKER_K8S_LOG_WINDOW_MINUTES", raising=False)
    config = K8sConfig.from_env()
    assert config.log_window_minutes == 5
    reader = KubernetesReader(config)
    result = reader.read_logs(K8sQuery())
    assert result["configured"] is False
    assert result.get("status") != "disabled"
    assert result["log_window_minutes"] == 5
    assert result["log_window_seconds"] == 300


def test_log_window_env_override(monkeypatch) -> None:
    monkeypatch.setenv("ROOTSEEKER_K8S_LOG_WINDOW_MINUTES", "12")
    assert K8sConfig.from_env().log_window_minutes == 12


def test_disabled_reader_does_not_call_api() -> None:
    def _boom(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("disabled reader must not call Kubernetes")

    reader = KubernetesReader(K8sConfig(), transport=httpx.MockTransport(_boom))
    result = reader.read_memory(K8sQuery(namespace="demo"))
    assert result["configured"] is False
    assert result.get("status") != "disabled"
    assert "ROOTSEEKER_K8S_ENABLED" in result["error"]


def test_enabled_without_credentials_is_not_ready() -> None:
    def _boom(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("not-ready reader must not call Kubernetes")

    reader = KubernetesReader(
        K8sConfig(enabled=True, api_server="", token=""),
        transport=httpx.MockTransport(_boom),
    )
    result = reader.status()
    assert result["configured"] is False
    assert result.get("status") != "disabled"
    assert "连接信息" in result["summary"]


def test_reader_collects_cpu_memory_disk_and_five_minute_logs() -> None:
    seen_log_windows: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/namespaces/demo/pods":
            return httpx.Response(200, json={"items": [_pod()]})
        if path == "/apis/metrics.k8s.io/v1beta1/namespaces/demo/pods":
            return httpx.Response(200, json={"items": [_metrics()]})
        if path == "/api/v1/nodes/node-1/proxy/stats/summary":
            return httpx.Response(200, json=_stats())
        if path == "/api/v1/namespaces/demo/pods/api-0/log":
            seen_log_windows.append(request.url.params["sinceSeconds"])
            return httpx.Response(200, text="ERROR boom\n")
        return httpx.Response(404, json={"message": f"missing {path}"})

    reader = KubernetesReader(_ready_config(), transport=httpx.MockTransport(handler))
    snapshot = reader.collect_snapshot(K8sQuery(namespace="demo", service_name="order-service"))

    assert snapshot["configured"] is True
    assert snapshot.get("status") != "disabled"
    assert snapshot["log_window_minutes"] == 5
    assert snapshot["log_window_seconds"] == 300
    assert seen_log_windows == ["300"]
    cpu = snapshot["cpu"]["items"][0]
    memory = snapshot["memory"]["items"][0]
    assert cpu["usage_cores"] == 0.2
    assert cpu["usage_ratio"] == 0.2
    assert memory["usage_ratio"] == 0.9
    disk_ratios = {item["scope"]: item["usage_ratio"] for item in snapshot["disk"]["items"]}
    assert disk_ratios["volume"] == 0.9
    assert disk_ratios["node_fs"] == 0.1
    resources = {item["resource"] for item in snapshot["anomalies"]}
    assert resources == {"memory", "disk"}
    assert snapshot["logs"]["items"][0]["line_count"] == 1
    assert "ERROR boom" in snapshot["logs"]["items"][0]["text"]


def test_since_minutes_overrides_env_window() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/pods"):
            return httpx.Response(200, json={"items": [_pod()]})
        if path.endswith("/log"):
            seen.append(request.url.params["sinceSeconds"])
            return httpx.Response(200, text="line\n")
        return httpx.Response(200, json={"items": []})

    reader = KubernetesReader(
        _ready_config(log_window_minutes=5),
        transport=httpx.MockTransport(handler),
    )
    result = reader.read_logs(K8sQuery(namespace="demo", pod="api-0", since_minutes=2))
    assert result["log_window_minutes"] == 2
    assert seen == ["120"]


def test_k8s_tools_are_registered_on_mcp() -> None:
    reader = KubernetesReader(_ready_config(), transport=httpx.MockTransport(_api))
    registry = ToolRegistry()
    register_internal_tools(
        registry,
        adapter=StubInternalToolAdapter.seeded_default(),
        k8s_reader=reader,
    )
    names = {spec.name for spec in registry.list_specs()}
    assert {
        "k8s.status",
        "k8s.read_cpu",
        "k8s.read_memory",
        "k8s.read_disk",
        "k8s.read_logs",
        "k8s.collect_snapshot",
    } <= names

    gateway = McpGateway(registry, PolicyGuard(), InMemoryAuditLog())
    missing = gateway.invoke(
        ToolCallRequest(
            case_id="case-k8s",
            step_id="status",
            skill_name="k8s-status",
            tool_name="k8s.status",
            arguments={},
        )
    )
    assert missing.ok
    assert missing.content["mcp_present"] is False
    assert "未扫描到 Kubernetes MCP 协议" in missing.content["summary"]

    skipped = gateway.invoke(
        ToolCallRequest(
            case_id="case-k8s",
            step_id="memory",
            skill_name="k8s-runtime",
            tool_name="k8s.read_memory",
            arguments={"namespace": "demo", "service_name": "order-service"},
        )
    )
    assert skipped.ok
    assert skipped.content["mcp_present"] is False
    assert "anomalies" not in skipped.content or skipped.content["anomalies"] == []

    registry.register_external(
        ToolSpec(
            name="ext.k8s.pods_top",
            description="pod metrics from kubernetes mcp",
            server_name="k8s",
            scope=ToolScope.EXTERNAL,
            tags=["external", "mcp", "mcp-server:k8s"],
        )
    )
    result = gateway.invoke(
        ToolCallRequest(
            case_id="case-k8s",
            step_id="memory",
            skill_name="k8s-runtime",
            tool_name="k8s.read_memory",
            arguments={"namespace": "demo", "service_name": "order-service"},
        )
    )
    assert result.ok
    assert result.content["mcp_present"] is True
    assert result.content["mcp_servers"] == ["k8s"]
    assert result.content["anomalies"][0]["resource"] == "memory"
    assert build_k8s_tools(registry, reader)[0][0].name == "k8s.status"


def _ready_config(*, log_window_minutes: int = 5) -> K8sConfig:
    return K8sConfig(
        enabled=True,
        api_server="http://k8s.test",
        token="token",
        verify_ssl=False,
        namespace="demo",
        log_window_minutes=log_window_minutes,
    )


def _api(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/api/v1/namespaces/demo/pods":
        return httpx.Response(200, json={"items": [_pod()]})
    if path == "/apis/metrics.k8s.io/v1beta1/namespaces/demo/pods":
        return httpx.Response(200, json={"items": [_metrics()]})
    if path == "/api/v1/nodes/node-1/proxy/stats/summary":
        return httpx.Response(200, json=_stats())
    if path.endswith("/log"):
        return httpx.Response(200, text="ERROR boom\n")
    return httpx.Response(404, json={"message": path})


def _pod() -> dict[str, object]:
    return {
        "metadata": {
            "name": "api-0",
            "namespace": "demo",
            "labels": {"app": "order-service"},
        },
        "spec": {
            "nodeName": "node-1",
            "containers": [
                {
                    "name": "api",
                    "resources": {"limits": {"cpu": "1", "memory": "100Mi"}},
                }
            ],
        },
    }


def _metrics() -> dict[str, object]:
    return {
        "metadata": {"name": "api-0", "namespace": "demo"},
        "containers": [{"name": "api", "usage": {"cpu": "200m", "memory": "90Mi"}}],
    }


def _stats() -> dict[str, object]:
    return {
        "node": {
            "nodeName": "node-1",
            "fs": {"usedBytes": 10 * 1024**3, "capacityBytes": 100 * 1024**3},
        },
        "pods": [
            {
                "podRef": {"name": "api-0", "namespace": "demo"},
                "ephemeral-storage": {"usedBytes": 1024, "capacityBytes": 10 * 1024},
                "volume": [{"name": "data", "usedBytes": 90, "capacityBytes": 100}],
            }
        ],
    }
