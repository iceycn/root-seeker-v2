# Kubernetes 运行时证据

## 协议扫描

读取前调用 `k8s.status`（helper: `k8s-status`），扫描外部 MCP 协议。

- `mcp_present=false`：没有 Kubernetes MCP。不要调用下面任何一个读取工具。
- `mcp_present=true`：按下面的工具读取。

## 工具

- `k8s.collect_snapshot`：CPU、内存、磁盘和日志窗口，异常分析优先用这个。
- `k8s.read_cpu`：容器 CPU 用量，以及相对 limit 的使用率。
- `k8s.read_memory`：容器内存用量，以及相对 limit 的使用率。
- `k8s.read_disk`：节点文件系统、Pod 临时存储、数据卷用量。
- `k8s.read_logs`：最近一段时间的容器日志。

## 参数线索

- `namespace`：告警里的命名空间。缺省时用 `ROOTSEEKER_K8S_NAMESPACE`，仍为空则查询全部命名空间。
- `service_name`：归一化后的服务名。匹配标签 `app`、`app.kubernetes.io/name`，或 Pod 名前缀。
- `pod`：已经明确的 Pod 名。
- `container`：只读某一个容器的日志。
- `since_minutes`：日志窗口（分钟）。不传则用 `ROOTSEEKER_K8S_LOG_WINDOW_MINUTES`，默认 5。
- `tail_lines`：每个容器最多保留的日志行数，默认 `ROOTSEEKER_K8S_LOG_TAIL_LINES`（500）。

## 结果怎么用

- `anomalies` 非空表示使用率达到 85% 及以上，应作为资源耗尽假设的证据。
- `mcp_present=false` 表示没有扫描到 Kubernetes MCP 协议。这不是故障。
- 集群内运行时，token 和 API 地址可以从 ServiceAccount 自动读取；仍需先扫到 Kubernetes MCP。

## 前序步骤

- `k8s.status` 必须先返回 `mcp_present=true`。
- `incident.normalize` 或 `catalog.resolve_service` 已经给出 `service_name` 时再查，缩小 Pod 范围。
