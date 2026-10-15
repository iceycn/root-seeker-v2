---
name: k8s-status
description: "扫描已注册的外部 MCP，判断有没有 Kubernetes 协议。没有则不要读取 CPU、内存、磁盘和日志。"
allowed-tools: k8s.status
metadata:
  role: helper
  evidence_type: other
---

# Kubernetes MCP 协议扫描

读取 CPU、内存、磁盘或容器日志之前，必须先调用 `k8s.status`。它只扫描当前已经注册的外部 MCP，不访问集群。

## 判定

- `mcp_present=false`：没有扫描到 Kubernetes MCP 协议。停止后续全部 `k8s.read_*` 与 `k8s.collect_snapshot`。这不是故障，不要写成资源耗尽，不要重试。
- `mcp_present=true`：`mcp_servers` 与 `mcp_tools` 列出命中的协议。可以继续读取。日志窗口见 `log_window_minutes`，默认 5 分钟。

命中条件：外部 MCP 的 server id、工具名或标签里包含 `k8s`、`kubernetes` 或 `kubectl`。内置的 `k8s.*` 工具本身不算协议。

详细准则见 `references/guide.md`。
