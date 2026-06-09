# T4 MCP 工具平面

## 1. 任务目标

本任务用于把 RootSeeker V2 的所有工具能力统一纳入 MCP 控制平面。

重构的关键不是“把工具搬过来”，而是建立一套统一的工具接入、描述、调用、治理机制，避免后续重新出现：

- 每个模块各自调工具
- 每个工具各自定义参数
- 每个工具各自做权限和超时

---

## 2. 范围

本任务覆盖：

- Tool 描述模型
- Tool 注册机制
- Internal Tool Gateway
- External MCP Adapter
- Policy Guard
- Tool 审计

本任务不覆盖：

- 所有外部平台一次性接完
- 工具市场
- 工具运营后台

---

## 3. 输入

- `T1` 的 `ToolSpec`、`ToolCallRequest`、`ToolCallResult`
- `T2` 的最小链路
- 现有 `root_seek` 中的内建工具经验
- 外部平台 MCP 适配需求

---

## 4. 输出

必须产出：

- Tool 契约
- `ToolRegistry`
- `McpGateway`
- `PolicyGuard`
- 审计机制
- 内部工具与外部工具统一调用路径

---

## 5. 一级拆解

### `T4.1` 建立 Tool 统一描述

统一工具元数据和参数 schema。

### `T4.2` 建立 Tool 注册中心

统一管理工具发现和注册。

### `T4.3` 建立统一调用网关

所有工具调用都通过同一入口。

### `T4.4` 建立权限与审计控制

把安全和治理收回到控制平面。

---

## 6. 二级拆解

## 6.1 `T4.1` Tool 统一描述

### 必须定义

- `name`
- `description`
- `scope`
- `parameters`
- `server_name`
- `tags`

### 建议补充

- `timeout_seconds`
- `readonly`
- `owner`
- `risk_level`
- `supports_stream`

### 文件任务

- `contracts/tool.py`
- `docs/mcp/tool-schema.md`

## 6.2 `T4.2` Tool 注册中心

### 模块任务

- 注册内部工具
- 注册外部工具
- 查询工具列表
- 按标签和权限分类工具

### 类文件任务

- `mcp_plane/registry.py`
- `mcp_plane/catalog.py`

## 6.3 `T4.3` 统一调用网关

### 模块任务

- 接收统一的 `ToolCallRequest`
- 路由到内部实现或外部 MCP Server
- 统一处理超时、异常、重试

### 类文件任务

- `mcp_plane/gateway.py`
- `mcp_plane/external_client.py`
- `mcp_plane/internal_dispatcher.py`

## 6.4 `T4.4` 权限与审计

### 模块任务

- 定义只读工具
- 定义高风险工具
- 定义审批型工具
- 记录审计事件

### 类文件任务

- `mcp_plane/policy_guard.py`
- `storage/audit_store.py`
- `contracts/audit.py`

---

## 7. 推荐工具分类

建议先分为以下大类：

- `log.*`
- `trace.*`
- `code.*`
- `deps.*`
- `topology.*`
- `vector.*`
- `analysis.*`
- `report.*`

同时按来源再分：

- `internal.*`
- `external.<server>.*`

---

## 8. 风险

- 如果工具 schema 不统一，后续无法标准化 Skill
- 如果权限控制不收口，后续会出现安全边界失控
- 如果内外工具不走同一路径，后续排查剧本会分叉

---

## 9. 验收标准

完成本任务时，应该满足：

- 系统能列出所有可用工具
- 系统能统一调用内部工具与外部 MCP 工具
- 工具调用具有统一请求和响应结构
- 工具调用能被审计
- 高风险工具可以被拦截或要求审批

---

## 10. 推荐实施顺序

1. 先定 `ToolSpec`
2. 再建 `ToolRegistry`
3. 再建 `McpGateway`
4. 再建 `PolicyGuard`
5. 最后接入外部平台工具
