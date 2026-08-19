# Skill 运行时 · YAML 步进器（已删除）

## 1. 业务目标

`execute_skill_flow` YAML 步进器**已删除**。默认排查不再逐步执行 sidecar 中的 14 步 YAML，也不再支持按 `start_from_step_index` 续跑。

**当前默认路径**是 Agent playbook：`PlaybookResolver` 选出当前主流程 Skill（`SKILL.md`），`AttemptRunner` 按 playbook 正文与 `allowed-tools` 规划并经 MCP Gateway 调工具，写入 Case / Evidence / Report。详见 [03-default-triage-flow.md](./03-default-triage-flow.md) 与 [09-agent-runtime.md](./09-agent-runtime.md)。

成功时：`AttemptRunner` 产出已完成的 Case，`skill_slug` / `selected_skills` 为当前 playbook 的 `name`。

失败时：Planner 失败、缺主流程、缺必需 env、工具不在 `allowed-tools` 内 → Case 失败并带明确错误码（如 `SKILL_PLANNER_FAILED`、`SKILL_DEFAULT_UNAVAILABLE`、`SKILL_ENV_MISSING`、`SKILL_TOOL_NOT_ALLOWED`），**不会**回退到已删除的步进器。

本文件只记录「步进器已删除」这一事实，不再描述 `_run_step` / sidecar YAML 循环。Skill 加载见 [04-skill-system.md](./04-skill-system.md)；MCP 路由见 [07-mcp-plane.md](./07-mcp-plane.md)。

## 2. 入口一览

| 入口类型 | 路径 / 符号 | 说明 |
| --- | --- | --- |
| 默认执行 | `rootseeker/agent_runtime/attempt_runner.py:AttemptRunner.run_once` | 唯一默认执行器；加载 playbook、注入 env、调 planner、MCP 执行 |
| Bootstrap 包装 | `rootseeker/bootstrap/runtime.py:DevRuntime.run_default_flow_from_case_request` | 转调 `run_agent_from_case_request`，再适配为 `DefaultFlowRunResult` |
| Flow 编排包装 | `rootseeker/flow_runtime/flow_executor.py:FlowExecutor.execute_default` | 仍包装上述 Agent 路径并组装 `ExecutionTrace`；**无** `execute_from_checkpoint` |
| 按步恢复（已删除） | Gateway `flow.resume` / `flow.step`、Task `FLOW_RESUME` / `FLOW_STEP`、CLI `resume` | 成功路径已删除；CLI `resume` 打印 `FLOW_STEP_UNSUPPORTED` 并以退出码 2 返回 |

已删除符号（勿再当作运行时入口）：

- `rootseeker/skill_runtime/flow_executor.py:execute_skill_flow`
- `plugins/builtin/default_log_triage_flow/runner.py:execute_default_log_triage_flow`

## 3. 主调用链

默认路径不再经过 YAML 步进循环。顺序为：入口 → `run_default_flow_from_case_request` → `AttemptRunner` → MCP → Case / Evidence / Report。逐步细节见 [03-default-triage-flow.md](./03-default-triage-flow.md) §3 与 [09-agent-runtime.md](./09-agent-runtime.md)。

## 4. 相关测试

| 测试文件 | 覆盖点 |
| --- | --- |
| `tests/unit/skill_runtime/test_execute_skill_flow_removed.py` | 包不再导出 `execute_skill_flow` |
| `tests/unit/agent_runtime/test_playbook_attempt.py` | Planner 失败不调用旧 Flow；`SKILL_TOOL_NOT_ALLOWED` / `SKILL_ENV_MISSING` |
| `tests/unit/flow_runtime/test_flow_executor.py` | `execute_default` 走 Agent；无 `execute_from_checkpoint` |
| `tests/unit/apps/test_cli_entrypoints.py` | CLI `resume` 返回 `FLOW_STEP_UNSUPPORTED` |

## 5. 与其他文档的关系

| 文档 | 关系 |
| --- | --- |
| [03-default-triage-flow.md](./03-default-triage-flow.md) | 默认排查主链路（Agent playbook） |
| [04-skill-system.md](./04-skill-system.md) | 标准 `SKILL.md` 发现 / 解析 / 注册，无 sidecar |
| [09-agent-runtime.md](./09-agent-runtime.md) | `AttemptRunner` / planner / 多 attempt |
