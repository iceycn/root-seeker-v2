# RootSeeker V2 代码实现提示词

你现在要基于现有蓝图文档实现 RootSeeker V2 代码。

> 当前仓库命名口径说明（与现有实现保持一致）：
> 默认 Flow 插件 ID 使用 `builtin.default_log_triage_flow`（下划线），
> 对应目录为 `plugins/builtin/default_log_triage_flow/`。

## 一、系统定位

RootSeeker V2 是一个企业级现网日志链路故障排查系统。

它不是一个通用 AI 助手平台，也不是简单复刻 OpenClaw。

正确理解是：

```text
OpenClaw 借鉴能力 = 底座能力层
RootSeeker V2 = 构建在这些底座能力之上的企业级故障排查应用
```

RootSeeker V2 要使用类似 OpenClaw 的基础能力来构建上层应用：

- Agent Runtime：作为排查执行内核
- Plugin System：作为能力注册与扩展机制
- Channel Routing：作为告警输入和通知输出通道
- Gateway：作为控制面和事件面
- CLI：作为调试、回放、诊断入口
- Cron：作为定时巡检、索引刷新、回放评估入口
- Infra：作为配置、密钥、日志、审计、安全、事件底座

这些基础能力共同支撑 RootSeeker V2 的核心业务目标：

> 对现网日志链路故障进行自动化排查、证据收集、根因分析、报告生成、通知、回放与评估。

## 二、技术栈选择

主技术栈使用 Python 3，建议兼容 Python >= 3.11。

优先使用：

- FastAPI：API 服务
- Pydantic v2：契约模型
- pydantic-settings：配置
- asyncio：异步任务
- pytest：测试
- PyYAML：读取 Skill / Plugin 配置
- MCP 协议思想：所有工具能力通过 MCP ToolCall 抽象

暂不使用 Java 作为主后端。Java 仅作为未来侧车或企业 SDK 适配层预留。

Node.js 仅作为未来 Console / UI 可选，不作为主执行内核。

## 三、必须先阅读的文档

开始编码前，必须先阅读这些总控文档：

- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-重构蓝图.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/00-子任务总览.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/17-V1能力对齐与迁移清单.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/18-日志数据面契约.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/19-服务目录与日志源映射.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/20-内置默认故障排查Flow.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/21-代码索引与仓库同步路线图.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/22-回放与评估基准.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/23-T14-Task与Flow运行时.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/24-T15-日志数据面任务树.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/25-T16-服务目录任务树.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/26-T17-代码索引插件任务树.md`
- `/Users/beisen/PycharmProjects/root-seeker-v2/rootseeker-v2-子任务/27-T18-回放与评估任务树.md`

但是不要把所有文档一次性塞进上下文。

实际编码时必须采用“小上下文能力包模式”：

- 每轮只选择一个能力包。
- 每轮只阅读该能力包相关的 1 到 5 个文档。
- 每轮只修改该能力包相关的 1 到 5 个文件。
- 每轮必须能独立测试或至少独立静态校验。
- 每轮结束后更新进度，再进入下一个能力包。

## 四、分层理解

请按以下分层实现系统。

### 1. 基础能力层

这层借鉴 OpenClaw 的设计，但用 Python 实现。

包含：

```text
agent_runtime/
plugin_system/
channel_routing/
gateway/
cli_commands/
cron/
infra_core/
observability/
config/
secrets/
```

它们提供通用能力：

- Agent 执行循环
- 插件声明和注册
- 通道接入与路由
- 控制面协议
- CLI 命令
- 定时任务
- 配置和密钥
- 审计和日志
- 系统事件

### 2. RootSeeker 应用层

这是 RootSeeker V2 的业务层。

包含：

```text
skill_system/
mcp_plane/
task_runtime/
flow_runtime/
service_catalog/
log_data/
code_index/
evidence/
analysis/
storage/
```

它们实现故障排查业务：

- Skill 编排排查步骤
- MCP 工具调用
- 服务目录解析
- 日志查询
- trace 查询
- 代码索引
- 证据构建
- 根因分析
- 报告生成
- 回放评估

### 3. 应用入口层

包含：

```text
apps/api/
apps/worker/
apps/scheduler/
apps/cli/
```

它们只负责入口，不直接写业务逻辑。

## 五、最高优先级约束

所有排查链路必须遵守：

```text
Case
-> Skill
-> Step
-> Plugin Capability
-> MCP ToolCall
-> Tool Result
-> Evidence
-> RootCauseEngine
-> CaseReport
```

严禁：

- 默认 Flow 直接调用 `SlsAdapter`
- 默认 Flow 直接调用 `ZoektAdapter` / `QdrantAdapter`
- Agent Runtime 绕过 Skill / Plugin 直接调用 MCP
- RootCauseEngine 直接触发日志、服务目录、trace、代码搜索或 LSP 查询
- 业务代码直接调用 Provider / Adapter / SDK
- 未经插件声明的临时工具进入生产链路

Provider、Adapter、SDK 只能作为 MCP 工具背后的底层实现细节。

## 六、默认故障排查 Flow

必须先跑通默认 Flow。

```text
原始告警 payload
-> CaseCreateRequest
-> builtin Skill: base/default-log-triage
-> bundled Flow Plugin: builtin.default_log_triage_flow
-> MCP catalog.resolve_service
-> MCP log.query_by_trace_id / log.query_by_template
-> MCP trace.get_chain
-> MCP code.search
-> EvidencePack
-> RootCauseEngine
-> CaseReport
-> MCP notify.send
-> AuditEvent
```

这个默认 Flow 是 RootSeeker V2 的最小可用产品路径。

## 七、首批实现范围

先实现最小闭环，不要一开始实现所有高级能力。

第一阶段必须完成：

### 1. 契约层

实现：

```text
contracts/
```

至少包含：

- Case
- Step
- Skill
- Tool
- Plugin
- Flow
- Task
- Evidence
- Report
- Audit
- ServiceCatalog
- LogQuery
- Repository
- Indexing
- Replay
- ExecutionTrace

### 2. 基础能力层最小实现

实现：

```text
agent_runtime/
plugin_system/
channel_routing/
gateway/
cron/
infra_core/
observability/
```

但先做最小版：

- Agent Runtime 可以执行一个 Flow
- Plugin System 可以注册 bundled plugin
- Channel Routing 可以处理一个 Webhook 输入
- Gateway 可以提供基本事件输出
- Cron 先预留接口
- Infra 先提供配置、日志、审计、SecretRef 的基础实现

### 3. RootSeeker 应用层最小实现

实现：

```text
skill_system/
mcp_plane/
task_runtime/
flow_runtime/
service_catalog/
log_data/
code_index/
evidence/
analysis/
storage/
```

必须跑通：

- 读取 builtin Skill
- 读取 bundled Flow Plugin
- 注册 MCP tools
- 调用服务目录工具
- 调用日志查询工具
- 调用 trace 工具
- 调用代码搜索工具
- 构建 EvidencePack
- 生成 CaseReport
- 记录 AuditEvent

### 4. 内置 Skill

实现：

```text
skills/builtin/base/default-log-triage/SKILL.md
```

它负责声明默认排查步骤。

### 5. 内置插件

实现：

```text
plugins/builtin/default_log_triage_flow/
plugins/builtin/service_catalog/
plugins/builtin/log_query/
plugins/builtin/code_index/
plugins/builtin/notify/
```

这些插件负责声明能力，并注册 MCP 工具。

### 6. 内置 MCP 工具

实现：

```text
mcp_servers/internal/
```

至少包含：

- `catalog.resolve_service`
- `catalog.get_log_sources`
- `log.query_by_trace_id`
- `log.query_by_template`
- `trace.get_chain`
- `code.search`
- `code.read`
- `index.get_status`
- `notify.send`

第一版可以用 mock / in-memory 数据，但必须走完整 MCP ToolCall 链路。

## 八、建议目录结构

```text
rootseeker/
├── contracts/
├── agent_runtime/
├── plugin_system/
├── channel_routing/
├── gateway/
├── cli_commands/
├── cron/
├── infra_core/
├── observability/
├── config/
├── secrets/
├── skill_system/
├── mcp_plane/
├── task_runtime/
├── flow_runtime/
├── service_catalog/
├── log_data/
├── code_index/
├── evidence/
├── analysis/
├── storage/
├── policies/
├── bootstrap/
apps/
├── api/
├── worker/
├── scheduler/
├── cli/
skills/
├── builtin/
plugins/
├── builtin/
mcp_servers/
├── internal/
tests/
├── unit/
├── integration/
├── replay/
```

## 九、实现顺序

严格按“小上下文能力包”顺序实现。

不要一次性实现完整系统。每一轮只选择一个能力包，读取对应文档，完成对应文件和测试。

### 能力包 0：工程骨架

目标：

- 创建项目结构
- 创建 `pyproject.toml`
- 创建基础包目录

只读文档：

- `00-子任务总览.md`
- `02-骨架工程与最小链路.md`
- `T2-bootstrap-skeleton/01-project-layout.md`

允许修改：

- `pyproject.toml`
- `README.md`
- `rootseeker/__init__.py`
- 基础空目录

完成标准：

- 项目可安装
- `pytest` 能启动

### 能力包 1：核心契约

目标：

- 定义系统核心 DTO 和状态对象

只读文档：

- `01-架构冻结与核心契约.md`
- `T1-core-contracts/README.md`
- 当前要实现的一个小目标文件，例如 `T1-core-contracts/02-case-contracts.md`

允许修改：

- `rootseeker/contracts/*.py`
- `tests/unit/contracts/*`

完成标准：

- 契约模型可实例化
- 基础序列化测试通过

### 能力包 2：内存存储与审计

目标：

- 先提供 in-memory store
- 为后续链路提供最小状态保存能力

只读文档：

- `17-V1能力对齐与迁移清单.md`
- `13-配置与基础设施.md`
- `T13-config-infra/README.md`

允许修改：

- `rootseeker/storage/*.py`
- `rootseeker/observability/*.py`
- `tests/unit/storage/*`

完成标准：

- Case、Evidence、Audit 可存取
- 审计事件可追加和查询

### 能力包 3：Plugin System 最小版

目标：

- 支持 bundled plugin 声明和能力注册

只读文档：

- `08-插件化流程系统.md`
- `T8-plugin-flow/README.md`
- `20-内置默认故障排查Flow.md`

允许修改：

- `rootseeker/plugin_system/*.py`
- `plugins/builtin/*`
- `tests/unit/plugin_system/*`

完成标准：

- 能加载 bundled plugin
- 能注册 plugin capability

### 能力包 4：Skill System 最小版

目标：

- 支持读取 builtin Skill
- 支持选择默认 Skill

只读文档：

- `03-Skill系统改造.md`
- `T3-skill-system/README.md`
- `20-内置默认故障排查Flow.md`

允许修改：

- `rootseeker/skill_system/*.py`
- `skills/builtin/base/default-log-triage/SKILL.md`
- `tests/unit/skill_system/*`

完成标准：

- 能扫描 builtin Skill
- 能选中 `base/default-log-triage`

### 能力包 5：MCP Plane 最小版

目标：

- 建立 ToolRegistry、McpGateway、PolicyGuard

只读文档：

- `04-MCP工具平面.md`
- `T4-mcp-plane/README.md`
- `00-子任务总览.md` 中的全局调用约束

允许修改：

- `rootseeker/mcp_plane/*.py`
- `mcp_servers/internal/*`
- `tests/unit/mcp_plane/*`

完成标准：

- 所有工具调用都经过 `McpGateway`
- 工具调用产生审计事件

### 能力包 6：Service Catalog

目标：

- 实现服务目录契约、插件和 MCP 工具

只读文档：

- `19-服务目录与日志源映射.md`
- `25-T16-服务目录任务树.md`
- `T16-service-catalog/README.md`

允许修改：

- `rootseeker/service_catalog/*.py`
- `plugins/builtin/service_catalog/*`
- `mcp_servers/internal/catalog_tools.py`
- `tests/unit/service_catalog/*`

完成标准：

- `catalog.resolve_service` 可通过 MCP 调用
- 返回 `ServiceCatalogEntry`
- 不允许直接读取服务目录绕过 MCP

### 能力包 7：Log Data Plane

目标：

- 实现日志查询契约、插件和 MCP 工具

只读文档：

- `18-日志数据面契约.md`
- `24-T15-日志数据面任务树.md`
- `T15-log-data-plane/README.md`

允许修改：

- `rootseeker/log_data/*.py`
- `plugins/builtin/log_query/*`
- `mcp_servers/internal/log_tools.py`
- `tests/unit/log_data/*`

完成标准：

- `log.query_by_trace_id` 可通过 MCP 调用
- `LogQueryResult` 可转为 Evidence
- 查询可审计

### 能力包 8：Code Index Plugin

目标：

- 实现代码索引插件和 mock 代码搜索工具

只读文档：

- `21-代码索引与仓库同步路线图.md`
- `26-T17-代码索引插件任务树.md`
- `T17-code-index-plugin/README.md`

允许修改：

- `rootseeker/code_index/*.py`
- `plugins/builtin/code_index/*`
- `mcp_servers/internal/code_tools.py`
- `tests/unit/code_index/*`

完成标准：

- `code.search` 可通过 MCP 调用
- 结果可转为 CodeEvidence

### 能力包 9：Evidence

目标：

- 把服务目录、日志、trace、代码结果收敛为 EvidencePack

只读文档：

- `05-证据与推理内核.md`
- `T5-evidence-analysis/README.md`
- `18-日志数据面契约.md`
- `21-代码索引与仓库同步路线图.md`

允许修改：

- `rootseeker/evidence/*.py`
- `tests/unit/evidence/*`

完成标准：

- 能构建 EvidencePack
- 能生成 ContextWindow

### 能力包 10：RootCauseEngine

目标：

- 实现只读 Evidence 的根因分析

只读文档：

- `T5-evidence-analysis/05-root-cause-engine.md`
- `20-内置默认故障排查Flow.md`

允许修改：

- `rootseeker/analysis/*.py`
- `tests/unit/analysis/*`

完成标准：

- RootCauseEngine 只能消费 EvidencePack / ContextWindow
- 不能调用 MCP、Provider、Adapter、SDK

### 能力包 11：Task / Flow Runtime

目标：

- 实现默认 Flow 的执行框架

只读文档：

- `23-T14-Task与Flow运行时.md`
- `20-内置默认故障排查Flow.md`
- `T14-task-flow-runtime/README.md`

允许修改：

- `rootseeker/task_runtime/*.py`
- `rootseeker/flow_runtime/*.py`
- `tests/unit/task_runtime/*`
- `tests/unit/flow_runtime/*`

完成标准：

- Flow 每一步有状态和 trace
- 工具调用通过 MCP

### 能力包 12：默认 Flow 闭环

目标：

- 跑通默认故障排查 Flow

只读文档：

- `20-内置默认故障排查Flow.md`
- `17-V1能力对齐与迁移清单.md`

允许修改：

- `plugins/builtin/default_log_triage_flow/*`
- `rootseeker/bootstrap/*`
- `tests/integration/test_default_flow.py`

完成标准：

- 从告警 payload 到 CaseReport 全链路跑通
- 全链路满足 `Case -> Skill -> Step -> Plugin Capability -> MCP ToolCall -> Evidence`

### 能力包 13：API 入口

目标：

- 提供最小 API

只读文档：

- `02-骨架工程与最小链路.md`
- `20-内置默认故障排查Flow.md`

允许修改：

- `apps/api/*`
- `tests/integration/test_api_default_flow.py`

完成标准：

- API 能创建 Case
- API 能触发默认 Flow
- API 能查询报告

### 能力包 14：Replay / Evaluation

目标：

- 支持最小回放测试

只读文档：

- `22-回放与评估基准.md`
- `27-T18-回放与评估任务树.md`
- `T18-replay-evaluation/README.md`

允许修改：

- `rootseeker/replay/*.py`
- `rootseeker/evaluation/*.py`
- `tests/replay/*`

完成标准：

- 至少一个 replay case 可执行
- replay 可验证默认 Flow 输出

## 十、每轮能力包执行规则

每轮实现时必须遵守：

1. 先声明本轮选择的能力包编号和目标。
2. 只读取该能力包列出的文档；如确需读取其它文档，先说明原因。
3. 只修改该能力包允许的文件范围。
4. 每轮优先实现最小可测试闭环。
5. 每轮必须添加或更新测试。
6. 每轮结束必须输出：
  - 修改了哪些文件
  - 跑了哪些测试
  - 是否满足本能力包完成标准
  - 下一个建议能力包

禁止：

- 一轮同时实现多个能力包。
- 一轮读入所有文档。
- 一轮生成几十个文件。
- 为了架构完整性提前实现暂不需要的高级能力。

## 十一、上下文控制策略

如果上下文变大，必须按以下策略裁剪：

1. 保留当前能力包文档。
2. 保留 `00-子任务总览.md` 中的全局调用约束。
3. 保留本轮涉及的接口文件。
4. 丢弃其它能力包细节。

每次恢复上下文时，只需要重新读取：

- 当前能力包文档
- 当前修改文件
- 当前测试文件

不要重新读取整个蓝图。

## 十、RootCauseEngine 约束

`RootCauseEngine` 只能消费：

- `EvidencePack`
- `ContextWindow`

它不能：

- 调用 MCP
- 调用 Provider
- 调用 Adapter
- 查询日志
- 查询服务目录
- 查询 trace
- 查询代码
- 查询 LSP

如果证据不足，它只能返回“证据不足”或请求上游补证。

## 十一、验收标准

完成第一阶段后，必须满足：

- 能接收一条标准 Webhook 告警
- 能创建 Case
- 能通过 builtin Skill 触发默认 Flow
- 默认 Flow 由 bundled Flow Plugin 执行
- 服务目录、日志查询、代码搜索、通知都通过 MCP ToolCall
- RootCauseEngine 不直接调用任何工具
- 能生成 EvidencePack
- 能生成 CaseReport
- 能记录 AuditEvent
- 能跑通至少一个 replay 测试
- 所有核心模块有 pytest 覆盖

## 十二、注意事项

- 不要把 OpenClaw 直接照搬成产品。
- OpenClaw 的能力是底座，不是业务目标。
- RootSeeker V2 是构建在这些底座上的企业级故障排查应用。
- 先实现默认 Flow，再扩展团队自定义 Skill。
- 先用 mock/in-memory 跑通链路，再接真实 SLS、Zoekt、Qdrant、LSP。
- 所有实现都应保持简单、可测试、可替换。

## 十三、当前阶段实现状态（2026-04）

当前仓库已经不再是仅“最小骨架”，新增了以下基础能力包：

- Gateway 控制面基础实现（协议帧、方法注册、订阅与广播）
- Channel Routing 基础实现（inbound normalizer、session key、router、outbound、安全校验）
- TaskRuntime 对 `CASE_RUN/CRON/REPLAY` 的统一执行入口
- MCP internal + external 统一调用路径
- Infra/Observability 基础实现（safe path/json、network guard、exec approval、secret resolver、redaction）

详细边界与 `Completed/Partial/Planned` 分级请以：

- `docs/implementation-status.md`

为准；后续实现任务应优先对齐该文件与 `README.md`，避免“文档 Done 但实现 Partial”的偏差。

