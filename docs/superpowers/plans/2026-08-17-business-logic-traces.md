# Business Logic Code-Trace Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 RootSeeker V2 每个业务域写出一份可跟随的代码调用链文档，全部放在 `docs/business-logic/`。

**Architecture:** 先由控制器（Grok 4.6）划定业务边界与文件归属，再按波次派发独立子代理阅读源码并写 MD。各文档互不改同一文件，因此可并行。最后由控制器写总览并交叉核对入口是否遗漏。

**Tech Stack:** 文档为 Markdown + mermaid；源码以 Python 3.11 / FastAPI 为主（`rootseeker/`、`apps/`、`mcp_servers/`、`plugins/`、`skills/`）。

## Global Constraints

- 输出目录仅限 `docs/business-logic/`（计划文件除外）。
- 每篇文档必须遵循 `docs/business-logic/_TEMPLATE.md`。
- 语言：简体中文。
- 只读分析业务代码；禁止修改 `rootseeker/`、`apps/`、`tests/` 等实现。
- 禁止 git commit / push。
- 禁止编造符号；找不到就写「未在代码中找到」。
- 子代理执行模型：用户要求 Auto；当前 Task 工具可用 slug 为 `inherit` / `composer-2.5-fast` / `cursor-grok-4.5-high-fast` / `cursor-grok-4.6-high-fast`。执行波次使用 `composer-2.5-fast`（最快可用档，对应 Auto 意图）。
- 控制器模型保持 Cursor Grok 4.6，只做拆分、派发、审阅与总览。

---

## File Structure

将创建：

| 文件 | 责任 |
| --- | --- |
| `docs/business-logic/_TEMPLATE.md` | 统一章节模板（已由控制器写好） |
| `docs/business-logic/00-overview.md` | 全链路地图 + 文档索引（最后写） |
| `docs/business-logic/01-bootstrap-wiring.md` | DevRuntime 装配与存储选择 |
| `docs/business-logic/02-contracts-state-machines.md` | 契约与 Case/Step 状态机 |
| `docs/business-logic/03-default-triage-flow.md` | 默认排查主链路（告警→报告→通知） |
| `docs/business-logic/04-skill-system.md` | Skill 发现、解析、注册、合成发布 |
| `docs/business-logic/05-skill-runtime-flow-executor.md` | 步骤执行、参数解析、checkpoint 恢复 |
| `docs/business-logic/06-plugin-system.md` | Plugin manifest、能力解析、内置 flow plugin |
| `docs/business-logic/07-mcp-plane.md` | 工具注册、策略、审批、内外部适配器 |
| `docs/business-logic/08-evidence-root-cause.md` | 证据组装、根因引擎、报告生成 |
| `docs/business-logic/09-agent-runtime.md` | LLM 工具规划、run loop、compaction |
| `docs/business-logic/10-channel-routing.md` | 入站归一化、路由、出站通知 |
| `docs/business-logic/11-gateway-control-plane.md` | WS/HTTP 控制面方法与鉴权 |
| `docs/business-logic/12-task-runtime.md` | CASE_RUN / CRON / REPLAY / FLOW_* 任务 |
| `docs/business-logic/13-cron-scheduler.md` | 定时解析、错峰、并发、调度循环 |
| `docs/business-logic/14-code-index.md` | 仓同步、Zoekt/Qdrant/GitNexus/LSP |
| `docs/business-logic/15-service-catalog-log-data.md` | 服务目录与日志查询平面 |
| `docs/business-logic/16-storage.md` | memory/sqlite/mysql 后端解析与读写 |
| `docs/business-logic/17-approval-governance-replay.md` | 审批、部署策略、回放与质量门禁 |
| `docs/business-logic/18-apps-api-admin-cli.md` | API / Admin / Worker / Scheduler / CLI 入口 |
| `docs/business-logic/19-observability-infra.md` | 审计、指标、健康、密钥、网络守卫 |

---

### Task 1: Bootstrap 装配链路

**Files:**
- Create: `docs/business-logic/01-bootstrap-wiring.md`

**Interfaces:**
- Consumes: `_TEMPLATE.md`
- Produces: DevRuntime 字段表与 `create_dev_runtime` 调用链

- [ ] **Step 1:** 阅读 `rootseeker/bootstrap/runtime.py`、`rootseeker/bootstrap/__init__.py`、`rootseeker/config/__init__.py`、`rootseeker/config/internal_adapter.py`、`rootseeker/infra_core/settings.py`
- [ ] **Step 2:** 按模板写出装配顺序：settings → adapter → tools → policy → gateway → stores
- [ ] **Step 3:** 说明 `ROOTSEEKER_STORAGE_BACKEND` 如何选出 memory/sqlite/mysql
- [ ] **Step 4:** 列出 `run_default_flow_from_case_request` 如何落到默认 flow 并写回 store

### Task 2: 契约与状态机

**Files:**
- Create: `docs/business-logic/02-contracts-state-machines.md`

- [ ] **Step 1:** 阅读 `rootseeker/contracts/` 全部模块与 `docs/architecture/state-machines.md`
- [ ] **Step 2:** 按 Case / Skill / Tool / Evidence / Flow / Task / Audit / Plugin 分组说明核心类型
- [ ] **Step 3:** 画出 Case 与 Step 允许转移，并指出 `validate_case_transition` / `validate_step_transition` 的调用点（grep）

### Task 3: 默认排查主链路

**Files:**
- Create: `docs/business-logic/03-default-triage-flow.md`

- [ ] **Step 1:** 阅读 `skills/builtin/flows/default-log-triage/rootseeker-skill.yaml`、`plugins/builtin/default_log_triage_flow/runner.py`、`rootseeker/skill_runtime/flow_executor.py`、`rootseeker/flow_runtime/runtime.py`、`rootseeker/flow_runtime/flow_executor.py`
- [ ] **Step 2:** 按 YAML `steps` 顺序展开每一步：action → MCP tool → handler/adapter → evidence
- [ ] **Step 3:** 标明 HTTP `POST /cases/run-default`、webhook、admin error chat 三条入口如何汇入同一 runner
- [ ] **Step 4:** 这是全书最重要的一篇，必须有完整 mermaid 主链

### Task 4: Skill 系统

**Files:**
- Create: `docs/business-logic/04-skill-system.md`

- [ ] **Step 1:** 阅读 `rootseeker/skill_system/`（discovery/parser/registry/composer/draft_builder/review/publisher/content_loader）
- [ ] **Step 2:** 覆盖：内置 skill 加载、frontmatter、过滤、草稿合成、评审、发布/回滚
- [ ] **Step 3:** 关联 `skills/builtin/` 目录布局

### Task 5: Skill Runtime 与 Flow 执行

**Files:**
- Create: `docs/business-logic/05-skill-runtime-flow-executor.md`

- [ ] **Step 1:** 阅读 `rootseeker/skill_runtime/` 与 `rootseeker/flow_runtime/`
- [ ] **Step 2:** 逐步写 `execute_skill_flow`：选 skill → 解析 step 参数（rule/LLM）→ 调 gateway → sanitize → evidence map → 写 checkpoint
- [ ] **Step 3:** 写清 `execute_from_checkpoint` / `resume_status` 三种恢复语义

### Task 6: Plugin 系统

**Files:**
- Create: `docs/business-logic/06-plugin-system.md`

- [ ] **Step 1:** 阅读 `rootseeker/plugin_system/` 与 `plugins/builtin/`
- [ ] **Step 2:** 写 manifest 发现、registry、capability 解析、与 skill `flow_plugin_id` 的绑定

### Task 7: MCP 平面

**Files:**
- Create: `docs/business-logic/07-mcp-plane.md`

- [ ] **Step 1:** 阅读 `rootseeker/mcp_plane/`、`mcp_servers/internal/`、`mcp_servers/external/`
- [ ] **Step 2:** 写 `McpGateway.invoke`：registry → PolicyGuard → adapter → audit
- [ ] **Step 3:** 列出内部 tool 名到 handler 的映射表；外部 SLS/Jaeger/Zoekt/Composite 的装配条件

### Task 8: 证据与根因

**Files:**
- Create: `docs/business-logic/08-evidence-root-cause.md`

- [ ] **Step 1:** 阅读 `rootseeker/evidence/`、`rootseeker/analysis/`
- [ ] **Step 2:** 写证据 pack 组装、假设生成/校验、加权、收敛、规则报告与 LLM 报告降级

### Task 9: Agent Runtime

**Files:**
- Create: `docs/business-logic/09-agent-runtime.md`

- [ ] **Step 1:** 阅读 `rootseeker/agent_runtime/`
- [ ] **Step 2:** 写 run loop、planner JSON、依赖调度、ToolCallLoop、失败回退到 default flow、compaction

### Task 10: 渠道路由

**Files:**
- Create: `docs/business-logic/10-channel-routing.md`

- [ ] **Step 1:** 阅读 `rootseeker/channel_routing/`
- [ ] **Step 2:** 写 inbound normalize（aliyun/sls/prometheus/webhook）→ session key → router → outbound adapters
- [ ] **Step 3:** 连接 `POST /webhook/{channel}` 与 `notify.send`

### Task 11: Gateway 控制面

**Files:**
- Create: `docs/business-logic/11-gateway-control-plane.md`

- [ ] **Step 1:** 阅读 `rootseeker/gateway/` 及 `methods/`
- [ ] **Step 2:** 写 HTTP handle 与 `/gateway/ws` 帧协议、鉴权、订阅广播
- [ ] **Step 3:** 列出 case/flow/skill/tool/approval 方法到实现文件的表

### Task 12: Task Runtime

**Files:**
- Create: `docs/business-logic/12-task-runtime.md`

- [ ] **Step 1:** 阅读 `rootseeker/task_runtime/`
- [ ] **Step 2:** 写 submit → queue → executor，覆盖 `CASE_RUN` `CRON` `REPLAY` `FLOW_RESUME` `FLOW_STEP`

### Task 13: Cron 调度

**Files:**
- Create: `docs/business-logic/13-cron-scheduler.md`

- [ ] **Step 1:** 阅读 `rootseeker/cron/` 与 `apps/scheduler/main.py`
- [ ] **Step 2:** 写 job spec、parser、state store、stagger、concurrency、retry、与 admin 配置的衔接

### Task 14: 代码索引

**Files:**
- Create: `docs/business-logic/14-code-index.md`

- [ ] **Step 1:** 阅读 `rootseeker/code_index/`
- [ ] **Step 2:** 写注册仓 → clone/pull → zoekt/qdrant/gitnexus → search/read/find_callers/LSP
- [ ] **Step 3:** 连接 API `/repos` 与 MCP `code.*` `graph.*` `index.*`

### Task 15: 服务目录与日志平面

**Files:**
- Create: `docs/business-logic/15-service-catalog-log-data.md`

- [ ] **Step 1:** 阅读 `rootseeker/service_catalog/`、`rootseeker/log_data/`
- [ ] **Step 2:** 写 resolve_service / log sources / query renderer / time window / evidence map

### Task 16: 存储

**Files:**
- Create: `docs/business-logic/16-storage.md`

- [ ] **Step 1:** 阅读 `rootseeker/storage/` 与 `docs/storage-sqlite.md`、`docs/storage-mysql.md`
- [ ] **Step 2:** 写 backend_resolve 与 case/evidence/report/task/checkpoint 各实现对照表

### Task 17: 审批、治理与回放

**Files:**
- Create: `docs/business-logic/17-approval-governance-replay.md`

- [ ] **Step 1:** 阅读 `rootseeker/policies/`、`rootseeker/governance/`、`rootseeker/replay/`、`rootseeker/evaluation/`
- [ ] **Step 2:** 写 ApprovalStore 生命周期、PolicyGuard、DeploymentPolicyOrchestrator、replay runner、quality gate

### Task 18: 应用入口

**Files:**
- Create: `docs/business-logic/18-apps-api-admin-cli.md`

- [ ] **Step 1:** 阅读 `apps/api/main.py`、`apps/admin/main.py`（按路由 grep）、`apps/worker/main.py`、`apps/scheduler/main.py`、`apps/cli/main.py`、`rootseeker/cli_commands/`
- [ ] **Step 2:** 按应用列出路由/命令 → 下游业务文档链接（不要把默认 flow 细节再写一遍）
- [ ] **Step 3:** Admin 错误排查助手、仓库发现/同步、cron 配置要有独立小节

### Task 19: 可观测性与基础设施

**Files:**
- Create: `docs/business-logic/19-observability-infra.md`

- [ ] **Step 1:** 阅读 `rootseeker/observability/`、`rootseeker/infra_core/`、`rootseeker/secrets/`
- [ ] **Step 2:** 写 health/metrics/audit/redaction、secret resolver、network/exec/fs 守卫、event bus

### Task 20: 总览索引

**Files:**
- Create: `docs/business-logic/00-overview.md`

**Interfaces:**
- Consumes: Task 1–19 已写好的文档标题与入口表

- [ ] **Step 1:** 画一张端到端 mermaid（告警/API/Admin/Cron → 默认 flow → 证据报告 → 通知）
- [ ] **Step 2:** 文档索引表：文档名、覆盖入口、关键符号
- [ ] **Step 3:** 「如何读」指引：新人先读 00 → 03 → 07 → 08
- [ ] **Step 4:** 核对 1–19 文件均存在且非空

---

## Execution Waves

独立文件，允许同波并行：

- Wave A: Tasks 1, 2, 4, 6, 10
- Wave B: Tasks 3, 5, 7, 8
- Wave C: Tasks 9, 11, 12, 13
- Wave D: Tasks 14, 15, 16, 17
- Wave E: Tasks 18, 19
- Wave F: Task 20（必须最后，由控制器或单独子代理在全部文档就位后执行）

## Self-Review

- Spec coverage: 实现状态文档中的 Completed 模块均有对应 Task。
- Placeholder scan: 任务均指向具体路径，无 TBD。
- Type consistency: 默认 flow 入口统一为 `execute_default_log_triage_flow` / `FlowRuntime.run_default`。
