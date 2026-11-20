"""Kubernetes runtime reader used by anomaly analysis."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest
import yaml

from mcp_servers.internal.handlers import register_internal_tools
from rootseeker.contracts.tool import ToolCallRequest, ToolScope, ToolSpec
from rootseeker.k8s.client import KubernetesApiClient
from rootseeker.k8s.config import K8sConfig
from rootseeker.k8s.quantities import parse_bytes, parse_cpu_cores
from rootseeker.k8s.reader import K8sQuery, KubernetesReader
from rootseeker.k8s.tools import build_k8s_tools
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog
from tests.support.stub_internal_adapter import StubInternalToolAdapter



@pytest.fixture(autouse=True)
def _isolate_k8s_env(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing-kubeconfig"
    monkeypatch.setenv("KUBECONFIG", str(missing))
    monkeypatch.setenv("ROOTSEEKER_K8S_KUBECONFIG", str(missing))
    for name in (
        "ROOTSEEKER_K8S_TOKEN",
        "ROOTSEEKER_K8S_API_SERVER",
        "ROOTSEEKER_K8S_CLIENT_CERT",
        "ROOTSEEKER_K8S_CLIENT_KEY",
        "ROOTSEEKER_K8S_CA_CERT",
        "ROOTSEEKER_K8S_CONTEXT",
        "ROOTSEEKER_K8S_NAMESPACE",
        "ROOTSEEKER_K8S_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)


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
    assert "连接信息" in result["error"]


def test_explicitly_disabled_env_blocks_ready_credentials(monkeypatch, tmp_path) -> None:
    kube = tmp_path / "config"
    _write_kubeconfig(kube, token="secret-token")
    monkeypatch.setenv("ROOTSEEKER_K8S_ENABLED", "false")
    monkeypatch.setenv("ROOTSEEKER_K8S_KUBECONFIG", str(kube))
    monkeypatch.delenv("KUBECONFIG", raising=False)
    config = K8sConfig.from_env()
    assert config.explicitly_disabled is True
    assert config.is_ready() is False
    result = KubernetesReader(config, transport=httpx.MockTransport(lambda req: httpx.Response(500))).status()
    assert "ROOTSEEKER_K8S_ENABLED 未开启" in result["error"]


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
    assert snapshot.get("warnings") in (None, [],)


def test_metrics_api_missing_falls_back_to_stats_as_warning() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/namespaces/demo/pods":
            return httpx.Response(200, json={"items": [_pod()]})
        if path.startswith("/apis/metrics.k8s.io/"):
            return httpx.Response(404, json={"message": "the server could not find the requested resource"})
        if path == "/api/v1/nodes/node-1/proxy/stats/summary":
            return httpx.Response(200, json=_stats_with_cpu_memory())
        return httpx.Response(404, json={"message": f"missing {path}"})

    reader = KubernetesReader(_ready_config(), transport=httpx.MockTransport(handler))
    result = reader.read_memory(K8sQuery(namespace="demo"))
    assert result["ok"] is True
    assert result["items"]
    assert result["errors"] == []
    assert any("metrics.k8s.io 不可用" in item for item in result["warnings"])
    assert "已改用 kubelet stats/summary" in result["summary"]
    assert "水位正常" in result["summary"] or result["items"]


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


def test_kubeconfig_client_certificate_is_ready(monkeypatch, tmp_path) -> None:
    kube = tmp_path / "config"
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    cert.write_text("CERT", encoding="utf-8")
    key.write_text("KEY", encoding="utf-8")
    ca.write_text("CA", encoding="utf-8")
    _write_kubeconfig(
        kube,
        server="https://k8s.test",
        client_cert=str(cert),
        client_key=str(key),
        ca_cert=str(ca),
        namespace="demo",
    )
    monkeypatch.delenv("ROOTSEEKER_K8S_ENABLED", raising=False)
    monkeypatch.delenv("ROOTSEEKER_K8S_TOKEN", raising=False)
    monkeypatch.delenv("ROOTSEEKER_K8S_API_SERVER", raising=False)
    monkeypatch.setenv("ROOTSEEKER_K8S_KUBECONFIG", str(kube))
    monkeypatch.delenv("KUBECONFIG", raising=False)
    config = K8sConfig.from_env()
    try:
        assert config.is_ready() is True
        assert config.auth_source == "kubeconfig"
        assert config.token == ""
        assert config.client_cert == str(cert)
        assert config.client_key == str(key)
        assert config.namespace == "demo"
        client = KubernetesApiClient(config, transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"kind": "PodList", "items": []})))
        try:
            payload = client.get_json("/api/v1/pods")
            assert payload["kind"] == "PodList"
        finally:
            client.close()
    finally:
        config.cleanup()


def test_kubeconfig_inline_data_materializes_cert_files(monkeypatch, tmp_path) -> None:
    kube = tmp_path / "config"
    _write_kubeconfig(
        kube,
        server="https://k8s.test",
        client_cert_data=base64.b64encode(b"CERT").decode("ascii"),
        client_key_data=base64.b64encode(b"KEY").decode("ascii"),
        ca_data=base64.b64encode(b"CA").decode("ascii"),
    )
    monkeypatch.delenv("ROOTSEEKER_K8S_ENABLED", raising=False)
    monkeypatch.setenv("ROOTSEEKER_K8S_KUBECONFIG", str(kube))
    monkeypatch.delenv("KUBECONFIG", raising=False)
    config = K8sConfig.from_env()
    try:
        assert config.is_ready() is True
        assert Path(config.client_cert).is_file()
        assert Path(config.client_key).is_file()
        assert Path(config.ca_cert).is_file()
        assert Path(config.client_cert).read_bytes() == b"CERT"
    finally:
        temps = config._temp_files
        config.cleanup()
        assert all(not Path(item).exists() for item in temps)


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
    assert missing.content["configured"] is False
    assert missing.content["ok"] is True
    assert missing.content["errors"] == []
    assert missing.content.get("status") != "disabled"
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
    assert skipped.content["ok"] is True
    assert skipped.content["errors"] == []
    assert skipped.content.get("status") != "disabled"
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


def test_k8s_skills_are_wired_into_default_playbook() -> None:
    from rootseeker.skill_system import build_registry_from_builtin_skills

    root = Path(__file__).resolve().parents[3]
    registry = build_registry_from_builtin_skills(root / "skills" / "builtin")
    status = registry.get("k8s-status")
    runtime = registry.get("k8s-runtime")
    playbook = registry.get("default-log-triage")
    assert status.bound_tools == ["k8s.status"]
    assert "k8s.collect_snapshot" in runtime.bound_tools
    assert "k8s.status" in playbook.bound_tools
    assert "k8s.collect_snapshot" in playbook.bound_tools


def _ready_config(*, log_window_minutes: int = 5) -> K8sConfig:
    return K8sConfig(
        enabled=True,
        api_server="http://k8s.test",
        token="token",
        verify_ssl=False,
        namespace="demo",
        log_window_minutes=log_window_minutes,
    )


def _write_kubeconfig(
    path: Path,
    *,
    server: str = "https://k8s.test",
    token: str | None = None,
    client_cert: str | None = None,
    client_key: str | None = None,
    client_cert_data: str | None = None,
    client_key_data: str | None = None,
    ca_cert: str | None = None,
    ca_data: str | None = None,
    namespace: str = "default",
) -> None:
    user: dict = {}
    if token:
        user["token"] = token
    if client_cert:
        user["client-certificate"] = client_cert
    if client_key:
        user["client-key"] = client_key
    if client_cert_data:
        user["client-certificate-data"] = client_cert_data
    if client_key_data:
        user["client-key-data"] = client_key_data
    cluster: dict = {"server": server}
    if ca_cert:
        cluster["certificate-authority"] = ca_cert
    if ca_data:
        cluster["certificate-authority-data"] = ca_data
    payload = {
        "apiVersion": "v1",
        "kind": "Config",
        "current-context": "demo",
        "clusters": [{"name": "demo", "cluster": cluster}],
        "users": [{"name": "demo", "user": user}],
        "contexts": [{"name": "demo", "context": {"cluster": "demo", "user": "demo", "namespace": namespace}}],
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")


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


def _stats_with_cpu_memory() -> dict[str, object]:
    body = _stats()
    body["pods"][0]["cpu"] = {"usageNanoCores": 200_000_000}
    body["pods"][0]["memory"] = {"workingSetBytes": 90 * 1024**2}
    body["pods"][0]["containers"] = [
        {
            "name": "api",
            "cpu": {"usageNanoCores": 200_000_000},
            "memory": {"workingSetBytes": 90 * 1024**2},
        }
    ]
    return body
