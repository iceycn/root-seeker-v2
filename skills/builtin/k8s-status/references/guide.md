# MCP 协议扫描

## 工具

- `k8s.status`：扫描已注册的外部 MCP，不访问业务 Pod。

## 怎么读结果

| 字段 | 没有 Kubernetes MCP | 已有 Kubernetes MCP |
| --- | --- | --- |
| `mcp_present` | `false` | `true` |
| `configured` | `false` | `true` |
| `mcp_servers` | `[]` | 命中的 server id |
| `mcp_tools` | `[]` | 命中的外部工具名 |

`mcp_present=false` 时，禁止调用：

- `k8s.read_cpu`
- `k8s.read_memory`
- `k8s.read_disk`
- `k8s.read_logs`
- `k8s.collect_snapshot`

这些读取工具自己也会再扫一次。没有协议时直接返回同一结论，不会请求集群。
