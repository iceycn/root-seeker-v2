# 文件级细化与 OpenClaw 对标

## 1. 文档目标

本文档按 `T1` 到 `T13` 的模块顺序，把每个目标继续细化到具体文件级别，并与 `openclaw-analysis` 中的分析文档做对比，标出：

- 已覆盖的借鉴点
- 仍然遗漏的模块
- 当前拆分过粗的地方
- 后续应该继续拆出的文件

对标目录：

- `/Users/beisen/PycharmProjects/openclaw-analysis`

---

## 2. 总体对标结论

### 2.1 已经纳入蓝图的 OpenClaw 能力

- Agent 主运行循环、Attempt、工具目录、上下文压缩
- 插件 manifest、插件发现、插件注册 API
- 通道、路由、Inbound / Outbound、Session Key
- Gateway 请求帧、响应帧、事件帧、广播与订阅
- CLI 命令注册、pre-action hooks、doctor/status
- Cron 调度、错峰、并发、重试恢复
- 配置 schema、SecretRef、Agent Events、System Presence、Logging

### 2.2 仍需补充的 OpenClaw 能力

| 遗漏能力 | OpenClaw 对标文档 | 建议归属 |
|---|---|---|
| `tasks` 任务执行系统 | `tasks/01-task-execution-system.ts.md`, `tasks/02-task-executor.ts.md` | `T2`、`T7`、`T12` |
| `flows` 流程管理系统 | `flows/01-flows-process-system.ts.md`, `flows/01-flows-system.ts.md` | `T8` |
| `hooks` 事件钩子系统 | `hooks/01-hooks-event-system.ts.md`, `hooks/01-hooks-system.ts.md` | `T8`、`T13` |
| `daemon` 守护服务 | `daemon/01-daemon-service-system.ts.md`, `daemon/01-daemon-service.ts.md` | `T2`、`T12`、`T13` |
| `process` 进程管理 | `process/01-process-management.ts.md` | `T13` |
| `secrets` 密钥运行时 | `secrets/01-secrets-runtime.ts.md`, `secrets/03-resolve.ts.md` | `T13` |
| `security` 安全审计 | `security/01-security-audit-system.ts.md`, `security/01-host-env-security-policy.ts.md` | `T4`、`T13` |
| `context-engine` 上下文引擎 registry | `context-engine/01-context-engine-registry.ts.md` | `T5`、`T7` |
| `mcp` 集成系统 | `mcp/01-mcp-integration-system.ts.md` | `T4` |
| `pairing` 节点配对 | `pairing/01-pairing-system.ts.md` | `T10`、`T13` |
| `status` 状态文本 | `status/01-status-overview.ts.md`, `status/02-status-text.ts.md` | `T10`、`T11`、`T13` |
| `node-host` 沙箱调用 | `node-host/01-node-host-invoke.ts.md` | `T4`、`T13` |

### 2.3 当前拆分仍然偏粗的地方

- `T2` 的 `minimal-chain` 仍然过粗，应拆成 `case-service`、`planner`、`executor`、`reporting`、`task-queue`。
- `T7` 的 `attempt-runner` 仍然过粗，应拆成 `history-builder`、`prompt-builder`、`model-router`、`streaming-runner`、`complete-runner`。
- `T8` 的 `flow-plugin` 仍然过粗，应拆成 `flow-contract`、`flow-registry`、`flow-runtime`、`flow-checkpoint`。
- `T10` 的 `server` 仍然过粗，应拆成 `http-server`、`ws-server`、`handshake`、`request-handler`、`broadcast-loop`。
- `T13` 的基础设施面太宽，应继续拆成 `config/`、`secrets/`、`infra_core/`、`observability/`、`security/` 五组。

---

## 3. T1 Core Contracts 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| 公共模型 | `rootseeker/contracts/common.py` | 基础模型、ID、时间、分页 | `types/01-types-definition-system.ts.md` | 已覆盖，但需补分页、排序 |
| 错误结构 | `rootseeker/contracts/errors.py` | 标准错误码、错误详情 | `gateway/06-gateway-protocol-design.ts.md` | 目前遗漏 |
| Case 契约 | `rootseeker/contracts/case.py` | Case、Step、状态、计划快照 | `tasks/01-task-execution-system.ts.md` | 已覆盖，但需补 task revision |
| Skill 契约 | `rootseeker/contracts/skill.py` | SkillSpec、步骤、草稿 | `skills/01-skills-detailed-analysis.ts.md` | 已覆盖 |
| Tool 契约 | `rootseeker/contracts/tool.py` | ToolSpec、请求、响应 | `agents/16-tool-catalog.ts.md`, `mcp/01-mcp-integration-system.ts.md` | 需补 tool schema 版本 |
| Evidence 契约 | `rootseeker/contracts/evidence.py` | EvidenceItem、Pack、ContextWindow | `agents/07-context-engine-architecture.ts.md` | 已覆盖，但需补引用关系 |
| Report 契约 | `rootseeker/contracts/report.py` | 报告结构、建议动作、结论 | `10-核心模块方法级分析.md` | 目前过粗 |
| Audit 契约 | `rootseeker/contracts/audit.py` | 审计事件结构 | `security/01-security-audit-system.ts.md` | 目前遗漏 |
| Review 契约 | `rootseeker/contracts/review.py` | Skill 审核状态和意见 | `plugins/11-install.ts.md` | 目前遗漏 |

建议新增文件：

- `rootseeker/contracts/session.py`
- `rootseeker/contracts/task.py`
- `rootseeker/contracts/gateway.py`
- `rootseeker/contracts/plugin.py`
- `rootseeker/contracts/channel.py`

---

## 4. T2 Bootstrap Skeleton 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| 工程入口 | `pyproject.toml` | Python 项目元信息 | `core/01-entry.ts.md` | 已覆盖 |
| 运行配置 | `rootseeker/bootstrap/config.py` | Settings、路径、环境 | `config/07-schema.ts.md` | 需补 schema |
| 容器装配 | `rootseeker/bootstrap/container.py` | 初始化 Store、Registry、Service | `bootstrap/01-bootstrap-startup-system.ts.md` | 需补启动阶段 |
| 启动流程 | `rootseeker/bootstrap/startup.py` | 初始化顺序、校验、迁移 | `bootstrap/01-bootstrap-init.ts.md` | 目前遗漏 |
| API 入口 | `apps/api/main.py` | FastAPI 应用入口 | `gateway/07-server.ts.md` | 已覆盖 |
| API 路由 | `apps/api/routes/cases.py` | Case HTTP API | `gateway/server-methods` 相关分析 | 需拆 |
| Worker 入口 | `apps/worker/main.py` | Worker 启动 | `tasks/02-task-executor.ts.md` | 目前过粗 |
| Scheduler 入口 | `apps/scheduler/main.py` | 定时任务入口 | `cron/01-cron-service.ts.md` | 需补 |
| Daemon 入口 | `apps/daemon/main.py` | 守护进程入口 | `daemon/01-daemon-service-system.ts.md` | 目前遗漏 |
| 最小链路测试 | `tests/integration/test_minimal_chain.py` | 骨架闭环测试 | `qa/01-qa-scenarios.ts.md` | 需补 |

建议把 `minimal-chain` 拆成：

- `rootseeker/supervisor/case_service.py`
- `rootseeker/case_runtime/planner.py`
- `rootseeker/case_runtime/task_queue.py`
- `rootseeker/step_engine/step_executor.py`
- `rootseeker/analysis/reporting.py`

---

## 5. T3 Skill System 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Skill schema | `skills/schemas/skill-frontmatter.yaml` | frontmatter 校验 | `skills/01-skills-detailed-analysis.ts.md` | 已覆盖 |
| Skill 模板 | `skills/templates/default_skill.md` | 新技能模板 | `agents-skills/01-maintainer-skills-system.ts.md` | 已覆盖 |
| Frontmatter | `rootseeker/skill_system/frontmatter.py` | YAML 解析 | `agents/06-skills-system.ts.md` | 已覆盖 |
| Registry | `rootseeker/skill_system/registry.py` | 扫描和注册技能 | `skills/01-skills-ecosystem.ts.md` | 已覆盖 |
| Cache | `rootseeker/skill_system/cache.py` | 缓存技能目录 | `agents/06-skills-system.ts.md` | 目前遗漏 |
| Filtering | `rootseeker/skill_system/filtering.py` | 条件过滤 | `agents/06-skills-system.ts.md` | 目前遗漏 |
| Composer | `rootseeker/skill_system/composer.py` | 技能组合 | `flows/01-flows-system.ts.md` | 需补 flow 关系 |
| Synthesizer | `rootseeker/skill_system/synthesizer.py` | 从 Case 生成草稿 | `agents-skills/01-maintainer-skills-system.ts.md` | 已覆盖 |
| Review | `rootseeker/skill_system/review.py` | 审核流程 | `plugins/11-install.ts.md` | 目前遗漏 |
| Publisher | `rootseeker/skill_system/publisher.py` | 发布技能 | `plugins/11-install.ts.md` | 目前遗漏 |

过粗点：

- `composer` 需要拆出 `trigger_matcher.py`、`condition_evaluator.py`、`skill_plan_builder.py`。
- `synthesizer` 需要拆出 `case_trace_extractor.py`、`draft_renderer.py`、`quality_gate.py`。

---

## 6. T4 MCP Plane 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Tool schema | `rootseeker/contracts/tool.py` | 工具声明和调用结构 | `agents/16-tool-catalog.ts.md` | 已覆盖 |
| Registry | `rootseeker/mcp_plane/registry.py` | 工具注册表 | `agents/05-tool-catalog-core.ts.md` | 已覆盖 |
| Catalog | `rootseeker/mcp_plane/catalog.py` | 工具目录输出 | `agents/16-tool-catalog.ts.md` | 目前遗漏 |
| Gateway | `rootseeker/mcp_plane/gateway.py` | 工具调用入口 | `mcp/01-mcp-integration-system.ts.md` | 已覆盖 |
| External Client | `rootseeker/mcp_plane/external_client.py` | 外部 MCP Server 调用 | `mcp/01-mcp-integration-system.ts.md` | 目前遗漏 |
| Internal Dispatcher | `rootseeker/mcp_plane/internal_dispatcher.py` | 内部工具分发 | `agents/13-bash-tools.ts.md` | 目前遗漏 |
| Policy Guard | `rootseeker/mcp_plane/policy_guard.py` | 权限和审批 | `security/01-host-env-security-policy.ts.md` | 已覆盖但偏粗 |
| Node Host | `rootseeker/mcp_plane/node_host.py` | 沙箱/节点执行适配 | `node-host/01-node-host-invoke.ts.md` | 目前遗漏 |
| Audit | `rootseeker/storage/audit_store.py` | 工具审计 | `security/01-security-audit-system.ts.md` | 需补 |

过粗点：

- `policy_guard.py` 应拆成 `permission_policy.py`、`approval_policy.py`、`risk_policy.py`。
- `external_client.py` 应拆出 `stdio_client.py`、`http_client.py`、`tool_schema_mapper.py`。

---

## 7. T5 Evidence Analysis 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Collector | `rootseeker/evidence/collector.py` | 收集工具输出和告警证据 | `context-engine/01-context-engine-registry.ts.md` | 目前遗漏 |
| Normalizer | `rootseeker/evidence/normalizer.py` | 统一证据结构 | `agents/14-context-engine.ts.md` | 目前遗漏 |
| Evidence Store | `rootseeker/storage/evidence_store.py` | 保存证据包 | `sessions/`、`context-engine` 文档 | 需补 |
| Indexer | `rootseeker/evidence/indexer.py` | 建全文/向量索引 | `memory/01-mmr-algorithm-system.ts.md` | 目前遗漏 |
| Search | `rootseeker/evidence/search.py` | Case 内证据检索 | `agents/06-mmr-algorithm-system.ts.md` | 目前遗漏 |
| Context Assembler | `rootseeker/evidence/context_assembler.py` | 组装上下文窗口 | `agents/07-context-engine-architecture.ts.md` | 已覆盖 |
| Summarizer | `rootseeker/analysis/summarizer.py` | 长证据摘要 | `agents/14-context-engine.ts.md` | 目前遗漏 |
| Root Cause Engine | `rootseeker/analysis/root_cause_engine.py` | 假设和结论 | `05-Agent代理核心模块分析.md` | 已覆盖但偏粗 |
| Hypothesis Ranker | `rootseeker/analysis/hypothesis_ranker.py` | 假设排序 | `deep-dive/01-algorithm-complexity-analysis.md` | 目前遗漏 |
| Verification | `rootseeker/analysis/verification.py` | 假设验证 | `tasks/02-task-executor.ts.md` | 目前遗漏 |
| Reporting | `rootseeker/analysis/reporting.py` | 报告输出 | `10-核心模块方法级分析.md` | 已覆盖 |

过粗点：

- `root_cause_engine.py` 应拆成 `hypothesis_generator.py`、`hypothesis_ranker.py`、`evidence_linker.py`、`conclusion_builder.py`。
- `context_assembler.py` 应拆成 `evidence_prioritizer.py`、`budget_trimmer.py`、`context_renderer.py`。

---

## 8. T6 Skill Operations 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Draft Builder | `rootseeker/skill_system/draft_builder.py` | 生成技能草稿 | `agents-skills/01-maintainer-skills-system.ts.md` | 目前遗漏 |
| Trace Extractor | `rootseeker/skill_system/case_trace_extractor.py` | 从 Case 抽取步骤 | `tasks/01-task-execution-system.ts.md` | 目前遗漏 |
| Draft Renderer | `rootseeker/skill_system/draft_renderer.py` | 渲染 SKILL.md | `skills/01-skills-detailed-analysis.ts.md` | 目前遗漏 |
| Review | `rootseeker/skill_system/review.py` | 审核状态机 | `plugins/11-install.ts.md` | 目前遗漏 |
| Publisher | `rootseeker/skill_system/publisher.py` | 发布技能 | `plugins/11-install.ts.md` | 目前遗漏 |
| Versioning | `rootseeker/skill_system/versioning.py` | 版本管理 | `infra/state-migrations` 相关文档 | 目前遗漏 |
| Rollback | `rootseeker/skill_system/rollback.py` | 回滚技能 | `plugins/11-install.ts.md` | 目前遗漏 |
| Evaluation | `rootseeker/analysis/evaluation.py` | 技能评估 | `qa/01-qa-scenarios.ts.md` | 目前遗漏 |

遗漏点：

- 需要 `SkillQualityGate`，防止低质量生成技能进入审核。
- 需要 `SkillDiff`，展示草稿与正式技能差异。

---

## 9. T7 Agent Runtime 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Entry | `rootseeker/agent_runtime/entry.py` | Agent 入口结构 | `05-Agent代理核心模块分析.md` | 已规划 |
| Runtime Services | `rootseeker/agent_runtime/runtime_services.py` | 注入 stores/tools/config/logger | `agents/05-pi-embedded-runtime.ts.md` | 已规划 |
| Run Context | `rootseeker/agent_runtime/run_context.py` | 运行上下文 | `agents/17-context-runtime-state.ts.md` | 需补 |
| Run Loop | `rootseeker/agent_runtime/run_loop.py` | 主运行循环 | `agents/04-pi-embedded-runner-run.ts.md` | 已规划 |
| Attempt Runner | `rootseeker/agent_runtime/attempt_runner.py` | 单轮推理 | `agents/03-pi-embedded-runner-core.ts.md` | 已规划但偏粗 |
| History Builder | `rootseeker/agent_runtime/history_builder.py` | 构建消息历史 | `agents/14-context-engine.ts.md` | 目前遗漏 |
| Prompt Builder | `rootseeker/agent_runtime/prompt_builder.py` | 构建提示 | `05-Agent代理核心模块分析.md` | 目前遗漏 |
| Model Router | `rootseeker/agent_runtime/model_router.py` | 模型选择 | `agents/12-models-config.ts.md` | 目前遗漏 |
| Tool Call Loop | `rootseeker/agent_runtime/tool_call_loop.py` | 工具调用循环 | `agents/16-tool-catalog.ts.md` | 已规划 |
| Context Compactor | `rootseeker/agent_runtime/context_compactor.py` | 上下文压缩 | `agents/14-context-engine.ts.md` | 已规划 |
| Subagent Registry | `rootseeker/agent_runtime/subagent_registry.py` | 子 Agent 注册 | `agents/04-subagent-registry-core.ts.md` | 目前遗漏 |

过粗点：

- `attempt_runner.py` 应拆成 `streaming_runner.py`、`complete_runner.py`、`attempt_result_parser.py`。
- 需要补 `model_auth.py` 和 `auth_profiles.py`，对标 OpenClaw 的模型认证体系。

---

## 10. T8 Plugin Flow 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Manifest | `rootseeker/plugin_system/manifest.py` | 插件声明结构 | `04-插件和Provider系统分析.md` | 已规划 |
| Discovery | `rootseeker/plugin_system/discovery.py` | 插件发现 | `plugins/01-plugins-registry-core.ts.md` | 已规划 |
| Loader | `rootseeker/plugin_system/loader.py` | 插件加载 | `plugins/09-plugins-loader.ts.md` | 需补 |
| Manifest Registry | `rootseeker/plugin_system/manifest_registry.py` | manifest 去重和合并 | `plugins/06-registry.ts.md` | 已规划 |
| Plugin API | `rootseeker/plugin_system/plugin_api.py` | 注册 API | `plugin-sdk/01-plugin-sdk-core.ts.md` | 已规划 |
| Plugin Runtime | `rootseeker/plugin_system/plugin_runtime.py` | 插件运行上下文 | `plugin-sdk/01-plugin-sdk-runtime-system.ts.md` | 需补 |
| Flow Contract | `rootseeker/plugin_system/flow_contract.py` | 流程插件契约 | `flows/01-flows-process-system.ts.md` | 目前遗漏 |
| Flow Registry | `rootseeker/plugin_system/flow_registry.py` | 流程插件注册 | `flows/01-flows-system.ts.md` | 目前遗漏 |
| Hooks | `rootseeker/plugin_system/hooks.py` | 插件 Hook | `hooks/01-hooks-system.ts.md` | 目前遗漏 |
| Hot Reload | `rootseeker/plugin_system/hot_reload.py` | 插件热加载 | `plugins/08-plugin-hot-loading-mechanism.ts.md` | 可选但建议预留 |

遗漏点：

- `flows` 和 `hooks` 没有单独落文件，需要补齐。
- 插件安装、禁用、启用状态需要 `plugin_store.py`。

---

## 11. T9 Channel Routing 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Channel Contract | `rootseeker/channel_routing/channel.py` | 通道契约 | `channels/03-types.plugin.ts.md` | 已规划 |
| Registry | `rootseeker/channel_routing/registry.py` | 通道注册 | `channels/05-channels-registry.ts.md` | 需补 |
| Inbound | `rootseeker/channel_routing/inbound.py` | 入站消息 | `03-通道和路由模块分析.md` | 已规划 |
| Normalizer | `rootseeker/channel_routing/normalizer.py` | 告警归一化 | `channels/04-multi-channel-communication-architecture.ts.md` | 已规划 |
| Router | `rootseeker/channel_routing/router.py` | 路由决策 | `routing/01-resolve-route.ts.md` | 已规划 |
| Binding | `rootseeker/channel_routing/bindings.py` | 绑定规则 | `edge-modules/01-bindings-compat-system.ts.md` | 需补 |
| Session Key | `rootseeker/channel_routing/session_key.py` | 会话键 | `channels/06-session.ts.md` | 已规划 |
| Outbound | `rootseeker/channel_routing/outbound.py` | 出站通知 | `03-通道和路由模块分析.md` | 已规划 |
| Target Resolver | `rootseeker/channel_routing/target_resolver.py` | 目标解析 | `03-通道和路由模块分析.md` | 需补 |
| Security | `rootseeker/channel_routing/security.py` | allowlist/security | `security/01-host-env-security-policy.ts.md` | 已规划 |

遗漏点：

- 需要 `channels/aliyun_alert.py`、`channels/webhook.py`、`channels/robot_wecom.py` 等具体适配文档。
- 需要 `configured_state.py`，对标 OpenClaw configured-state。

---

## 12. T10 Gateway Control Plane 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Protocol | `rootseeker/gateway/protocol.py` | req/res/event 帧 | `gateway/06-gateway-protocol-design.ts.md` | 已规划 |
| Errors | `rootseeker/gateway/errors.py` | 网关错误 | `gateway/06-gateway-protocol-design.ts.md` | 需补 |
| Server | `rootseeker/gateway/server.py` | 网关服务入口 | `gateway/07-server.ts.md` | 已规划但偏粗 |
| Runtime State | `rootseeker/gateway/runtime_state.py` | clients、dedupe、abort | `gateway/05-server.impl.ts.md` | 已规划 |
| Connection | `rootseeker/gateway/connection.py` | 握手和认证 | `06-Gateway网关模块分析.md` | 已规划 |
| Message Handler | `rootseeker/gateway/message_handler.py` | 处理 frame | `06-Gateway网关模块分析.md` | 目前遗漏 |
| Method Registry | `rootseeker/gateway/method_registry.py` | 方法注册 | `gateway/06-gateway-protocol-design.ts.md` | 已规划 |
| Broadcaster | `rootseeker/gateway/broadcaster.py` | 广播事件 | `06-Gateway网关模块分析.md` | 已规划 |
| Subscriptions | `rootseeker/gateway/subscriptions.py` | 订阅管理 | `gateway/06-gateway-protocol-design.ts.md` | 已规划 |
| Pairing | `rootseeker/gateway/pairing.py` | 节点配对 | `pairing/01-pairing-system.ts.md` | 目前遗漏 |

过粗点：

- `server.py` 应拆成 `http_server.py`、`ws_server.py`、`startup.py`。
- 需要 `gateway/methods/` 目录按 `case.py`、`skill.py`、`tool.py`、`system.py` 拆分。

---

## 13. T11 CLI Commands 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Command Catalog | `rootseeker/cli_commands/catalog.py` | 命令目录 | `cli/01-cli-command-system.ts.md` | 已规划 |
| Context | `rootseeker/cli_commands/context.py` | CLI 上下文 | `cli/02-build-program.ts.md` | 已规划 |
| Pre Action | `rootseeker/cli_commands/pre_action.py` | 前置钩子 | `02-CLI和命令模块分析.md` | 已规划 |
| Config Guard | `rootseeker/cli_commands/config_guard.py` | 配置守卫 | `02-CLI和命令模块分析.md` | 已规划 |
| Case Commands | `rootseeker/cli_commands/commands/case.py` | Case 命令 | `10-核心模块方法级分析.md` | 已规划 |
| Skill Commands | `rootseeker/cli_commands/commands/skill.py` | Skill 命令 | `agents/20-cli.ts.md` | 已规划 |
| Tool Commands | `rootseeker/cli_commands/commands/tool.py` | Tool 命令 | `agents/20-cli.ts.md` | 已规划 |
| Plugin Commands | `rootseeker/cli_commands/commands/plugin.py` | 插件命令 | `plugins/14-cli.ts.md` | 已规划 |
| Channel Commands | `rootseeker/cli_commands/commands/channel.py` | 通道命令 | `02-CLI和命令模块分析.md` | 已规划 |
| Doctor | `rootseeker/cli_commands/commands/doctor.py` | 诊断 | `commands/01-commands-doctor.ts.md` | 已规划 |

遗漏点：

- 需要 `commands/config.py` 对标 OpenClaw config-cli。
- 需要 `commands/gateway.py` 对标 gateway-cli。
- 需要 `commands/cron.py` 管理定时任务。

---

## 14. T12 Cron Scheduler 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Contracts | `rootseeker/cron/contracts.py` | Job、State、Result | `cron/01-cron-scheduling-system.ts.md` | 已规划 |
| Schedule | `rootseeker/cron/schedule.py` | cron 解析 | `cron/01-cron-scheduling-system.ts.md` | 已规划 |
| Scheduler | `rootseeker/cron/scheduler.py` | 调度主逻辑 | `cron/01-cron-service.ts.md` | 已规划 |
| Timer | `rootseeker/cron/timer.py` | 唤醒与执行循环 | `cron/01-cron-service.ts.md` | 目前遗漏 |
| Stagger | `rootseeker/cron/stagger.py` | 错峰 | `cron/01-cron-scheduling-system.ts.md` | 已规划 |
| Concurrency | `rootseeker/cron/concurrency.py` | 并发控制 | `cron/01-cron-scheduling-system.ts.md` | 已规划 |
| Retry | `rootseeker/cron/retry.py` | 失败重试 | `cron/01-cron-scheduling-system.ts.md` | 已规划 |
| Recovery | `rootseeker/cron/recovery.py` | 陈旧状态恢复 | `cron/01-cron-service.ts.md` | 已规划 |
| State Store | `rootseeker/cron/state_store.py` | 状态持久化 | `cron/01-cron-service.ts.md` | 已规划 |

遗漏点：

- 需要 `cron/jobs/` 目录，拆出 `skill_evaluation.py`、`index_refresh.py`、`health_check.py`、`case_replay.py`。
- 需要 `cron/locks.py`，为未来分布式调度预留。

---

## 15. T13 Config Infra 文件级细化

| 模块目标 | 具体文件 | 文件职责 | OpenClaw 对标 | 判断 |
|---|---|---|---|---|
| Config Schema | `rootseeker/config/schema.py` | schema 合并 | `config/07-schema.ts.md` | 已规划 |
| Validation | `rootseeker/config/validation.py` | 配置校验 | `08-配置和基础设施模块分析.md` | 已规划 |
| Loader | `rootseeker/config/loader.py` | 配置 I/O | `08-配置和基础设施模块分析.md` | 需补 |
| Runtime Config | `rootseeker/config/runtime.py` | 运行时快照 | `config/01-types-openclaw-core.ts.md` | 需补 |
| Secret Ref | `rootseeker/secrets/ref.py` | SecretRef 契约 | `secrets/01-secrets-runtime.ts.md` | 已规划 |
| Secret Resolver | `rootseeker/secrets/resolver.py` | env/file/exec 解析 | `secrets/03-resolve.ts.md` | 已规划 |
| Safe FS | `rootseeker/infra_core/fs_safe.py` | 安全文件操作 | `infra/01-core-infrastructure.ts.md` | 已规划 |
| Atomic JSON | `rootseeker/infra_core/json_files.py` | 原子写入 | `infra/01-core-infrastructure.ts.md` | 已规划 |
| Exec Approval | `rootseeker/infra_core/exec_approval.py` | 执行审批 | `infra/01-deep-infrastructure.ts.md` | 已规划 |
| Network Guard | `rootseeker/infra_core/network_guard.py` | SSRF 防护 | `infra/01-infra-overview.ts.md` | 已规划 |
| Agent Events | `rootseeker/infra_core/agent_events.py` | 事件总线 | `infra/01-agent-events.ts.md` | 已规划 |
| System Presence | `rootseeker/infra_core/system_presence.py` | 节点状态 | `infra/02-system-presence.ts.md` | 已规划 |
| Logger | `rootseeker/observability/logger.py` | 日志 | `logging/01-logging-system.ts.md` | 已规划 |
| Redaction | `rootseeker/observability/redaction.py` | 脱敏 | `logging/01-logging-system.ts.md` | 已规划 |
| State Migration | `rootseeker/infra_core/state_migrations.py` | 状态迁移 | `infra/01-infra-overview.ts.md` | 目前遗漏 |
| Process Manager | `rootseeker/infra_core/process_manager.py` | 进程管理 | `process/01-process-management.ts.md` | 目前遗漏 |

过粗点：

- `network_guard.py` 应拆成 `ssrf.py`、`proxy.py`、`request_guard.py`。
- `exec_approval.py` 应拆成 `approval_policy.py`、`approval_forwarder.py`、`allowlist.py`。
- `logger.py` 应拆成 `config.py`、`transport.py`、`diagnostic.py`。

---

## 16. 建议新增一级任务

对标 OpenClaw 后，原建议在 `T1-T13` 之外新增若干任务。其中 `Task / Flow Runtime` 已升级为正式 `T14`，日志数据面、服务目录、代码索引、回放评估也已分别升级为 `T15` 到 `T18`。

### `T14` Task / Flow Runtime

原因：

- OpenClaw 的 `tasks` 和 `flows` 是核心系统模块。
- RootSeeker V2 目前把流程分散在 `case_runtime`、`agent_runtime`、`plugin_system` 中，仍然可能偏散。

建议文件：

- `rootseeker/task_runtime/task.py`
- `rootseeker/task_runtime/task_executor.py`
- `rootseeker/task_runtime/task_registry.py`
- `rootseeker/flow_runtime/flow_contract.py`
- `rootseeker/flow_runtime/flow_executor.py`
- `rootseeker/flow_runtime/checkpoint.py`

状态：

- 已由 `23-T14-Task与Flow运行时.md` 承接。

### 后续候选：Security / Compliance

原因：

- OpenClaw 有独立 `security` 分析。
- RootSeeker 作为企业级故障排查系统，会访问生产日志、trace、代码和密钥。

建议文件：

- `rootseeker/security/audit_engine.py`
- `rootseeker/security/policy.py`
- `rootseeker/security/data_access.py`
- `rootseeker/security/pii_redaction.py`
- `rootseeker/security/compliance_report.py`

建议编号：

- 如后续需要独立一级任务，建议使用 `T19`，避免与当前 `T15` 日志数据面冲突。

### 后续候选：UI / Console

原因：

- OpenClaw 有 UI、TUI、Canvas、Mobile 多端。
- RootSeeker V2 至少需要 Console 或运维后台查看 Case、Agent Events、Skill、Tools。

建议文件：

- `apps/console/`
- `rootseeker/gateway/methods/console.py`
- `rootseeker/contracts/ui.py`

建议编号：

- 如后续需要独立一级任务，建议使用 `T20`，避免与当前 `T16` 服务目录冲突。

---

## 17. 下一步推荐

建议先按以下顺序继续拆：

1. 把 `T7-agent-runtime/README.md` 拆成 `run-loop.md`、`attempt-runner.md`、`tool-call-loop.md`。
2. 把 `T8-plugin-flow/README.md` 拆成 `manifest.md`、`flow-plugin.md`、`hooks.md`。
3. 把 `T10-gateway-control-plane/README.md` 拆成 `protocol.md`、`server.md`、`methods.md`。
4. 把 `T13-config-infra/README.md` 拆成 `config.md`、`secrets.md`、`logging.md`、`security.md`。
5. `T14-task-flow-runtime` 已补齐；后续如果继续扩展，优先考虑 `T19-security-compliance` 和 `T20-ui-console`。
