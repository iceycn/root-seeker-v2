# 内置默认故障排查 Flow

## 1. 目标

RootSeeker V2 必须提供一条零自定义可用的内置默认 Flow，对齐现有 `root_seek` 的直连分析链路。

这个 Flow 的目标是保证系统即使没有团队自定义 Skill、没有额外插件，也能完成一次基础现网日志链路故障排查。

强制架构约束：

- 默认 Flow 必须由 builtin Skill 触发。
- 默认 Flow 必须由 bundled Flow Plugin 承载。
- 默认 Flow 内部的服务目录、日志查询、trace 查询、代码索引、通知发送都必须通过 MCP 工具执行。
- 默认 Flow 不允许直接调用 Provider、Adapter 或底层 SDK。
- 内置 MCP 工具也不能绕过 Skill 和插件被默认 Flow 直接调用。

---

## 2. 默认 Flow

```text
接收告警
  -> builtin Skill: base/default-log-triage
  -> bundled Flow Plugin: builtin.default-log-triage-flow
  -> MCP catalog.resolve_service
  -> MCP log.query_by_trace_id / log.query_by_template
  -> MCP trace.get_chain
  -> MCP code.search / lsp.*
  -> EvidencePack
  -> RootCause 分析
  -> CaseReport
  -> MCP notify.send
  -> AuditEvent
```

---

## 3. Flow 输入

- 原始告警 payload
- 或标准 `CaseCreateRequest`
- 或历史回放样本

---

## 4. Flow 输出

- `CaseRecord`
- `EvidencePack`
- `RootCauseConclusion`
- `CaseReport`
- `AuditEvent[]`

---

## 5. 默认步骤

### Step 1：告警归一化

输出：

- `NormalizedAlert`

### Step 2：服务解析

输出：

- `ServiceCatalogEntry`

### Step 3：日志补全

输出：

- `LogQueryResult[]`

### Step 4：Trace 补全

输出：

- `TraceChainEvidence`

### Step 5：代码证据检索

输出：

- `CodeEvidence`

### Step 6：证据包构建

输出：

- `EvidencePack`

### Step 7：直连根因分析

输出：

- `RootCauseConclusion`

### Step 8：报告与通知

输出：

- `CaseReport`
- `NotificationResult`

---

## 6. 与 Skill / Plugin 的关系

默认 Flow 不等于绕过 Skill 和 Plugin。

约束：

- 默认 Flow 必须被包装成 builtin Skill：`base/default-log-triage`
- 默认 Flow 必须被注册成 bundled Flow Plugin：`builtin.default-log-triage-flow`
- 默认 Flow 的每一步工具调用都必须通过 MCP
- 内置 MCP 工具只能由 Skill Step 或 Flow Plugin 调用
- 团队自定义 Flow 只能替换某些步骤，不能破坏审计和权限
- 默认 Flow 永远作为兜底路径保留

禁止事项：

- 禁止默认 Flow 直接调用 `SlsAdapter`
- 禁止默认 Flow 直接调用 `ZoektAdapter` 或 `QdrantAdapter`
- 禁止默认 Flow 直接读取服务目录存储
- 禁止 RootCauseEngine 自行触发代码或日志查询

---

## 7. 归属任务

- `T2`：最小链路必须跑通默认 Flow 的缩小版
- `T5`：证据和根因分析
- `T7`：Agent 深度模式可在默认 Flow 后增强
- `T8`：默认 Flow 作为 bundled flow plugin
- `T9`：告警输入和通知输出
- `T13`：审计、日志脱敏、配置

---

## 8. 验收标准

- 无团队自定义 Skill 时，系统仍可分析一条标准告警
- 无复杂 Agent 多轮推理时，系统仍可输出报告
- 默认 Flow 可回放
- 默认 Flow 每一步都有输入输出和审计
- 默认 Flow 能覆盖 `root_seek` 的直连分析主链路

