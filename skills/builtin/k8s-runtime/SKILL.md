---
name: k8s-runtime
description: "扫描到 Kubernetes MCP 协议后，读取 CPU、内存、磁盘和一段时间内容器日志，供异常分析使用。"
allowed-tools: k8s.collect_snapshot k8s.read_cpu k8s.read_memory k8s.read_disk k8s.read_logs
metadata:
  role: helper
  evidence_type: metric
---

# Kubernetes 读取

先按 helper `k8s-status` 调用 `k8s.status`，扫描已注册的外部 MCP。只有 `mcp_present=true` 才继续读取。没有 Kubernetes MCP 协议时立即停止，不要把空结果当成故障。

## 读取

已扫描到协议时优先调用一次 `k8s.collect_snapshot`。它同时返回 CPU、内存、磁盘和日志窗口。需要单独核对时再调用单项工具。

- `k8s.read_cpu`：容器 CPU 用量，以及相对 limit 的使用率。
- `k8s.read_memory`：容器内存用量，以及相对 limit 的使用率。
- `k8s.read_disk`：节点文件系统、Pod 临时存储、数据卷用量。
- `k8s.read_logs`：最近一段时间的容器日志。

日志窗口来自 `ROOTSEEKER_K8S_LOG_WINDOW_MINUTES`，默认 5 分钟。单次可用 `since_minutes` 覆盖。

## 参数

- `namespace`：告警中的命名空间。缺省用 `ROOTSEEKER_K8S_NAMESPACE`，仍为空则查全部命名空间。
- `service_name`：归一化后的服务名。匹配标签 `app`、`app.kubernetes.io/name`，或 Pod 名前缀。
- `pod`：已经明确的 Pod 名。
- `container`：只读某一个容器的日志。
- `tail_lines`：每个容器最多保留的日志行数，默认 500。

## 结果

- `anomalies` 非空：使用率达到 85% 及以上，作为资源耗尽证据。
- `mcp_present=false`：没有 Kubernetes MCP 协议，丢弃该结果。
- `configured=false`：没有可用的 Kubernetes 证据。

详细准则见 `references/guide.md`。
