"""Read Kubernetes CPU, memory, disk and a recent log window for anomaly analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from rootseeker.k8s.client import KubernetesApiClient, KubernetesApiError
from rootseeker.k8s.config import K8sConfig
from rootseeker.k8s.quantities import format_bytes, format_cores, parse_bytes, parse_cpu_cores

__all__ = ["K8sQuery", "KubernetesReader"]

PRESSURE_RATIO = 0.85
MAX_RESOURCE_PODS = 50
MAX_LOG_PODS = 5
MAX_STAT_NODES = 10
MAX_LOG_CHARS = 32_000


@dataclass
class K8sQuery:
    namespace: str = ""
    pod: str = ""
    service_name: str = ""
    container: str = ""
    label_selector: str = ""
    since_minutes: int | None = None
    tail_lines: int | None = None

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> K8sQuery:
        return cls(
            namespace=_text(args, "namespace", "ns"),
            pod=_text(args, "pod", "pod_name"),
            service_name=_text(args, "service_name", "service"),
            container=_text(args, "container"),
            label_selector=_text(args, "label_selector"),
            since_minutes=_positive_int(args.get("since_minutes")),
            tail_lines=_positive_int(args.get("tail_lines")),
        )

    def resolved_namespace(self, config: K8sConfig) -> str:
        return self.namespace or config.namespace

    def window_minutes(self, config: K8sConfig) -> int:
        chosen = self.since_minutes if self.since_minutes is not None else config.log_window_minutes
        return max(1, min(int(chosen), 24 * 60))

    def resolved_tail_lines(self, config: K8sConfig) -> int:
        chosen = self.tail_lines if self.tail_lines is not None else config.log_tail_lines
        return max(1, min(int(chosen), 5000))


@dataclass
class _ContainerView:
    name: str
    cpu_limit: float | None
    memory_limit: int | None
    cpu_limit_raw: str
    memory_limit_raw: str


@dataclass
class _PodView:
    name: str
    namespace: str
    node_name: str
    labels: dict[str, str]
    containers: list[_ContainerView] = field(default_factory=list)


@dataclass
class _Inspection:
    pods: list[_PodView]
    items: list[dict[str, Any]]
    errors: list[str]


class KubernetesReader:
    """Collect pod/node resource samples and container logs."""

    def __init__(
        self,
        config: K8sConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or K8sConfig.from_env()
        self._transport = transport
        self._client: KubernetesApiClient | None = None

    @classmethod
    def from_env(cls) -> KubernetesReader:
        return cls(K8sConfig.from_env())

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def status(self) -> dict[str, Any]:
        """Report whether Kubernetes reads are enabled before any API call."""
        window = self.config.log_window_minutes
        body: dict[str, Any] = {
            "kind": "status",
            "log_window_minutes": window,
            "log_window_seconds": window * 60,
            "items": [],
            "anomalies": [],
        }
        if not self.config.enabled:
            reason = "ROOTSEEKER_K8S_ENABLED 未开启"
            body.update(
                {
                    "configured": False,
                    "ok": False,
                    "summary": "Kubernetes 客户端未配置，跳过读取。",
                    "error": reason,
                    "errors": [reason],
                }
            )
            return body
        if not self.config.is_ready():
            reason = self.config.disabled_reason()
            body.update(
                {
                    "configured": False,
                    "ok": False,
                    "summary": "Kubernetes 客户端缺少连接信息，跳过读取。",
                    "error": reason,
                    "errors": [reason],
                }
            )
            return body
        body.update(
            {
                "configured": True,
                "ok": True,
                "summary": f"Kubernetes 客户端可用。日志窗口 {window} 分钟。",
                "errors": [],
            }
        )
        return body

    def read_cpu(self, query: K8sQuery | None = None) -> dict[str, Any]:
        return self._read_resource("cpu", query or K8sQuery())

    def read_memory(self, query: K8sQuery | None = None) -> dict[str, Any]:
        return self._read_resource("memory", query or K8sQuery())

    def read_disk(self, query: K8sQuery | None = None) -> dict[str, Any]:
        return self._read_resource("disk", query or K8sQuery())

    def read_logs(self, query: K8sQuery | None = None) -> dict[str, Any]:
        current = query or K8sQuery()
        blocked = self._blocked(current, "logs")
        if blocked is not None:
            return blocked
        try:
            pods = self._list_pods(current)
        except KubernetesApiError as exc:
            return self._failed(current, "logs", str(exc))
        return self._logs_for(pods[:MAX_LOG_PODS], current, truncated_pods=len(pods) > MAX_LOG_PODS)

    def collect_snapshot(self, query: K8sQuery | None = None) -> dict[str, Any]:
        """CPU, memory, disk and the configured log window, for anomaly analysis."""
        current = query or K8sQuery()
        blocked = self._blocked(current, "snapshot")
        if blocked is not None:
            return blocked
        cpu = self.read_cpu(current)
        memory = self.read_memory(current)
        disk = self.read_disk(current)
        logs = self.read_logs(current)
        anomalies = [
            *(cpu.get("anomalies") or []),
            *(memory.get("anomalies") or []),
            *(disk.get("anomalies") or []),
        ]
        errors = [
            *(cpu.get("errors") or []),
            *(memory.get("errors") or []),
            *(disk.get("errors") or []),
            *(logs.get("errors") or []),
        ]
        window = current.window_minutes(self.config)
        if anomalies:
            summary = "；".join(str(item.get("detail") or "") for item in anomalies[:5])
            summary = f"{summary}。日志窗口 {window} 分钟"
        else:
            summary = f"未发现 cpu / memory / disk 压力。日志窗口 {window} 分钟"
        return {
            "configured": True,
            "ok": bool(cpu.get("ok") or memory.get("ok") or disk.get("ok") or logs.get("ok")),
            "kind": "snapshot",
            "namespace": current.resolved_namespace(self.config),
            "service_name": current.service_name,
            "log_window_minutes": window,
            "log_window_seconds": window * 60,
            "cpu": cpu,
            "memory": memory,
            "disk": disk,
            "logs": logs,
            "anomalies": anomalies,
            "summary": summary,
            "errors": errors,
        }

    def _read_resource(self, kind: str, query: K8sQuery) -> dict[str, Any]:
        blocked = self._blocked(query, kind)
        if blocked is not None:
            return blocked
        try:
            inspection = self._inspect(query)
        except KubernetesApiError as exc:
            return self._failed(query, kind, str(exc))
        items = [item for item in inspection.items if item.get("kind") == kind]
        anomalies = _anomalies(items)
        summary = _resource_summary(kind, items, anomalies)
        return self._ok(
            query,
            kind=kind,
            items=items,
            anomalies=anomalies,
            summary=summary,
            errors=inspection.errors,
        )

    def _blocked(self, query: K8sQuery, kind: str) -> dict[str, Any] | None:
        if self.config.is_ready():
            return None
        blocked = self.status()
        window = query.window_minutes(self.config)
        blocked["kind"] = kind
        blocked["log_window_minutes"] = window
        blocked["log_window_seconds"] = window * 60
        return blocked

    def _failed(self, query: K8sQuery, kind: str, error: str) -> dict[str, Any]:
        window = query.window_minutes(self.config)
        return {
            "configured": True,
            "ok": False,
            "kind": kind,
            "log_window_minutes": window,
            "log_window_seconds": window * 60,
            "items": [],
            "anomalies": [],
            "summary": error,
            "errors": [error],
        }

    def _ok(
        self,
        query: K8sQuery,
        *,
        kind: str,
        items: list[dict[str, Any]],
        anomalies: list[dict[str, Any]],
        summary: str,
        errors: list[str],
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        window = query.window_minutes(self.config)
        body = {
            "configured": True,
            "ok": bool(items) or not errors,
            "kind": kind,
            "namespace": query.resolved_namespace(self.config),
            "service_name": query.service_name,
            "log_window_minutes": window,
            "log_window_seconds": window * 60,
            "items": items,
            "anomalies": anomalies,
            "summary": summary,
            "errors": errors,
        }
        if extra:
            body.update(extra)
        return body

    def _api(self) -> KubernetesApiClient:
        if self._client is None:
            self._client = KubernetesApiClient(self.config, transport=self._transport)
        return self._client

    def _inspect(self, query: K8sQuery) -> _Inspection:
        pods = self._list_pods(query)[:MAX_RESOURCE_PODS]
        errors: list[str] = []
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        metrics_error = self._append_metrics(query, pods, items, seen)
        if metrics_error:
            errors.append(metrics_error)
        errors.extend(self._append_stats(pods, items, seen, fill_cpu_memory=bool(metrics_error)))
        return _Inspection(pods=pods, items=items, errors=errors)

    def _list_pods(self, query: K8sQuery) -> list[_PodView]:
        namespace = query.resolved_namespace(self.config)
        if namespace:
            path = f"/api/v1/namespaces/{_seg(namespace)}/pods"
        else:
            path = "/api/v1/pods"
        params: dict[str, str] = {}
        if query.label_selector:
            params["labelSelector"] = query.label_selector
        payload = self._api().get_json(path, params)
        pods = [_parse_pod(item) for item in _items(payload)]
        pods = [pod for pod in pods if pod is not None and _matches(pod, query)]
        return pods

    def _append_metrics(
        self,
        query: K8sQuery,
        pods: list[_PodView],
        items: list[dict[str, Any]],
        seen: set[tuple[str, str, str, str]],
    ) -> str:
        namespace = query.resolved_namespace(self.config)
        if namespace:
            path = f"/apis/metrics.k8s.io/v1beta1/namespaces/{_seg(namespace)}/pods"
        else:
            path = "/apis/metrics.k8s.io/v1beta1/pods"
        try:
            payload = self._api().get_json(path)
        except KubernetesApiError as exc:
            return f"metrics.k8s.io 不可用: {exc}"
        by_pod = {(pod.namespace, pod.name): pod for pod in pods}
        for metric in _items(payload):
            meta = _dict(metric.get("metadata"))
            key = (str(meta.get("namespace") or ""), str(meta.get("name") or ""))
            pod = by_pod.get(key)
            if pod is None:
                continue
            limits = {container.name: container for container in pod.containers}
            for container in metric.get("containers") or []:
                if not isinstance(container, dict):
                    continue
                name = str(container.get("name") or "")
                usage = _dict(container.get("usage"))
                spec = limits.get(name)
                cpu = parse_cpu_cores(usage.get("cpu"))
                memory = parse_bytes(usage.get("memory"))
                if cpu is not None:
                    _add_cpu(items, seen, pod, name, cpu, spec, source="metrics", raw=str(usage.get("cpu")))
                if memory is not None:
                    _add_memory(
                        items,
                        seen,
                        pod,
                        name,
                        memory,
                        spec,
                        source="metrics",
                        raw=str(usage.get("memory")),
                    )
        return ""

    def _append_stats(
        self,
        pods: list[_PodView],
        items: list[dict[str, Any]],
        seen: set[tuple[str, str, str, str]],
        *,
        fill_cpu_memory: bool,
    ) -> list[str]:
        errors: list[str] = []
        selected = {(pod.namespace, pod.name): pod for pod in pods}
        nodes = []
        for pod in pods:
            if pod.node_name and pod.node_name not in nodes:
                nodes.append(pod.node_name)
        for node in nodes[:MAX_STAT_NODES]:
            path = f"/api/v1/nodes/{_seg(node)}/proxy/stats/summary"
            try:
                summary = self._api().get_json(path)
            except KubernetesApiError as exc:
                errors.append(f"节点 {node} 磁盘统计不可用: {exc}")
                continue
            node_body = _dict(summary.get("node"))
            fs = _dict(node_body.get("fs"))
            disk = _disk_item(
                scope="node_fs",
                namespace="",
                pod="",
                node=str(node_body.get("nodeName") or node),
                volume="",
                used=fs.get("usedBytes"),
                capacity=fs.get("capacityBytes"),
            )
            if disk is not None:
                items.append(disk)
            for pod_stats in summary.get("pods") or []:
                if not isinstance(pod_stats, dict):
                    continue
                ref = _dict(pod_stats.get("podRef"))
                key = (str(ref.get("namespace") or ""), str(ref.get("name") or ""))
                pod = selected.get(key)
                if pod is None:
                    continue
                ephemeral = _dict(pod_stats.get("ephemeral-storage"))
                disk = _disk_item(
                    scope="pod_ephemeral",
                    namespace=pod.namespace,
                    pod=pod.name,
                    node=pod.node_name,
                    volume="",
                    used=ephemeral.get("usedBytes"),
                    capacity=ephemeral.get("capacityBytes"),
                )
                if disk is not None:
                    items.append(disk)
                for volume in pod_stats.get("volume") or []:
                    if not isinstance(volume, dict):
                        continue
                    disk = _disk_item(
                        scope="volume",
                        namespace=pod.namespace,
                        pod=pod.name,
                        node=pod.node_name,
                        volume=str(volume.get("name") or ""),
                        used=volume.get("usedBytes"),
                        capacity=volume.get("capacityBytes"),
                    )
                    if disk is not None:
                        items.append(disk)
                if not fill_cpu_memory:
                    continue
                limits = {container.name: container for container in pod.containers}
                for container in pod_stats.get("containers") or []:
                    if not isinstance(container, dict):
                        continue
                    name = str(container.get("name") or "")
                    spec = limits.get(name)
                    cpu_stats = _dict(container.get("cpu"))
                    nano = cpu_stats.get("usageNanoCores")
                    if isinstance(nano, (int, float)):
                        _add_cpu(items, seen, pod, name, float(nano) / 1_000_000_000, spec, source="stats")
                    memory_stats = _dict(container.get("memory"))
                    working = memory_stats.get("workingSetBytes", memory_stats.get("usageBytes"))
                    if isinstance(working, (int, float)):
                        _add_memory(items, seen, pod, name, int(working), spec, source="stats")
        return errors

    def _logs_for(
        self,
        pods: list[_PodView],
        query: K8sQuery,
        *,
        truncated_pods: bool,
    ) -> dict[str, Any]:
        window = query.window_minutes(self.config)
        tail = query.resolved_tail_lines(self.config)
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        if not pods:
            return self._ok(
                query,
                kind="logs",
                items=[],
                anomalies=[],
                summary="未找到匹配的 Pod，无法读取日志。",
                errors=[],
            )
        for pod in pods:
            containers = [query.container] if query.container else [c.name for c in pod.containers]
            if not containers:
                containers = [""]
            for container in containers:
                params = {
                    "sinceSeconds": str(window * 60),
                    "timestamps": "true",
                    "tailLines": str(tail),
                }
                if container:
                    params["container"] = container
                path = f"/api/v1/namespaces/{_seg(pod.namespace)}/pods/{_seg(pod.name)}/log"
                try:
                    text = self._api().get_text(path, params)
                except KubernetesApiError as exc:
                    errors.append(f"{pod.namespace}/{pod.name}:{container or '*'} 日志读取失败: {exc}")
                    continue
                truncated = False
                if len(text) > MAX_LOG_CHARS:
                    text = text[:MAX_LOG_CHARS]
                    truncated = True
                lines = text.splitlines()
                if len(lines) >= tail:
                    truncated = True
                items.append(
                    {
                        "namespace": pod.namespace,
                        "pod": pod.name,
                        "container": container,
                        "line_count": len(lines),
                        "truncated": truncated,
                        "text": text,
                    }
                )
        line_count = sum(int(item["line_count"]) for item in items)
        summary = f"读取 {len(items)} 个容器最近 {window} 分钟日志，共 {line_count} 行"
        if truncated_pods:
            summary += f"（仅前 {MAX_LOG_PODS} 个 Pod）"
        extra = {"truncated": truncated_pods or any(item["truncated"] for item in items)}
        body = self._ok(
            query,
            kind="logs",
            items=items,
            anomalies=[],
            summary=summary,
            errors=errors,
            extra=extra,
        )
        body.pop("anomalies", None)
        return body


def _text(args: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = args.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        try:
            number = int(value)
        except ValueError:
            return None
    else:
        return None
    if number <= 0:
        return None
    return number


def _seg(value: str) -> str:
    return quote(value, safe="")


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(payload: dict[str, Any]) -> list[Any]:
    raw = payload.get("items")
    return raw if isinstance(raw, list) else []


def _parse_pod(raw: object) -> _PodView | None:
    if not isinstance(raw, dict):
        return None
    meta = _dict(raw.get("metadata"))
    name = str(meta.get("name") or "")
    namespace = str(meta.get("namespace") or "")
    if not name or not namespace:
        return None
    spec = _dict(raw.get("spec"))
    labels = {str(key): str(val) for key, val in _dict(meta.get("labels")).items()}
    containers: list[_ContainerView] = []
    for container in spec.get("containers") or []:
        if not isinstance(container, dict):
            continue
        resources = _dict(container.get("resources"))
        limits = _dict(resources.get("limits"))
        containers.append(
            _ContainerView(
                name=str(container.get("name") or ""),
                cpu_limit=parse_cpu_cores(limits.get("cpu")),
                memory_limit=parse_bytes(limits.get("memory")),
                cpu_limit_raw=str(limits.get("cpu") or ""),
                memory_limit_raw=str(limits.get("memory") or ""),
            )
        )
    return _PodView(
        name=name,
        namespace=namespace,
        node_name=str(spec.get("nodeName") or ""),
        labels=labels,
        containers=containers,
    )


def _matches(pod: _PodView, query: K8sQuery) -> bool:
    if query.pod and pod.name != query.pod:
        return False
    if query.namespace and pod.namespace != query.namespace:
        return False
    service = query.service_name
    if not service:
        return True
    if pod.labels.get("app") == service or pod.labels.get("app.kubernetes.io/name") == service:
        return True
    return pod.name == service or pod.name.startswith(f"{service}-")


def _ratio(used: float | None, limit: float | None) -> float | None:
    if used is None or limit is None or limit <= 0:
        return None
    return used / limit


def _add_cpu(
    items: list[dict[str, Any]],
    seen: set[tuple[str, str, str, str]],
    pod: _PodView,
    container: str,
    cores: float,
    spec: _ContainerView | None,
    *,
    source: str,
    raw: str = "",
) -> None:
    key = (pod.namespace, pod.name, container, "cpu")
    if key in seen:
        return
    seen.add(key)
    limit = spec.cpu_limit if spec else None
    items.append(
        {
            "kind": "cpu",
            "namespace": pod.namespace,
            "pod": pod.name,
            "container": container,
            "node": pod.node_name,
            "usage_cores": cores,
            "limit_cores": limit,
            "usage_ratio": _ratio(cores, limit),
            "usage": raw or format_cores(cores),
            "limit": (spec.cpu_limit_raw if spec and spec.cpu_limit_raw else format_cores(limit)),
            "source": source,
        }
    )


def _add_memory(
    items: list[dict[str, Any]],
    seen: set[tuple[str, str, str, str]],
    pod: _PodView,
    container: str,
    used: int,
    spec: _ContainerView | None,
    *,
    source: str,
    raw: str = "",
) -> None:
    key = (pod.namespace, pod.name, container, "memory")
    if key in seen:
        return
    seen.add(key)
    limit = spec.memory_limit if spec else None
    items.append(
        {
            "kind": "memory",
            "namespace": pod.namespace,
            "pod": pod.name,
            "container": container,
            "node": pod.node_name,
            "usage_bytes": used,
            "limit_bytes": limit,
            "usage_ratio": _ratio(float(used), float(limit) if limit else None),
            "usage": raw or format_bytes(used),
            "limit": (spec.memory_limit_raw if spec and spec.memory_limit_raw else format_bytes(limit)),
            "source": source,
        }
    )


def _disk_item(
    *,
    scope: str,
    namespace: str,
    pod: str,
    node: str,
    volume: str,
    used: object,
    capacity: object,
) -> dict[str, Any] | None:
    if not isinstance(used, (int, float)) and not isinstance(capacity, (int, float)):
        return None
    used_bytes = int(used) if isinstance(used, (int, float)) else None
    capacity_bytes = int(capacity) if isinstance(capacity, (int, float)) else None
    return {
        "kind": "disk",
        "scope": scope,
        "namespace": namespace,
        "pod": pod,
        "node": node,
        "volume": volume,
        "used_bytes": used_bytes,
        "capacity_bytes": capacity_bytes,
        "usage_ratio": _ratio(
            float(used_bytes) if used_bytes is not None else None,
            float(capacity_bytes) if capacity_bytes is not None else None,
        ),
        "source": "stats",
    }


def _anomalies(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in items:
        ratio = item.get("usage_ratio")
        if not isinstance(ratio, (int, float)) or ratio < PRESSURE_RATIO:
            continue
        found.append(
            {
                "resource": item.get("kind"),
                "target": _target(item),
                "usage_ratio": round(float(ratio), 4),
                "detail": _pressure_detail(item),
            }
        )
    return found


def _target(item: dict[str, Any]) -> str:
    scope = str(item.get("scope") or "")
    if scope == "node_fs":
        return str(item.get("node") or "")
    base = "/".join(part for part in (item.get("namespace"), item.get("pod")) if part)
    extra = str(item.get("container") or item.get("volume") or "")
    if scope == "pod_ephemeral":
        extra = extra or "ephemeral-storage"
    if extra:
        return f"{base}:{extra}" if base else extra
    return base


def _pressure_detail(item: dict[str, Any]) -> str:
    ratio = float(item["usage_ratio"])
    pct = f"{ratio * 100:.0f}%"
    kind = str(item.get("kind") or "resource")
    if kind == "cpu":
        return f"cpu 使用率 {pct}（{item.get('usage')}/{item.get('limit') or '无上限'}）"
    if kind == "memory":
        return (
            f"memory 使用率 {pct}"
            f"（{format_bytes(item.get('usage_bytes'))}/{format_bytes(item.get('limit_bytes'))}）"
        )
    return (
        f"disk 使用率 {pct}"
        f"（{format_bytes(item.get('used_bytes'))}/{format_bytes(item.get('capacity_bytes'))}）"
    )


def _resource_summary(kind: str, items: list[dict[str, Any]], anomalies: list[dict[str, Any]]) -> str:
    if anomalies:
        return "；".join(str(item.get("detail") or "") for item in anomalies[:5])
    if not items:
        return f"未读到 {kind} 数据"
    return f"{kind} 水位正常，共 {len(items)} 条"
