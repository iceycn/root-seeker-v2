# Business Logic 重审与 Bug 修复计划（第二轮）

> **控制器：** Grok 4.6（规划与审阅）  
> **子任务：** Auto / inherit（禁止 fast 模式）  
> **目标：** 对照当前代码重审 `docs/business-logic/01–19`，修正过时描述；按链路排查并修复生产路径 bug。

**Global Constraints**

- 文档目录：`docs/business-logic/`
- 遵循 `_TEMPLATE.md`
- 简体中文
- 每波次 ≤4 篇文档，避免单次上下文过大
- 修复 bug 后跑 `pytest tests/unit tests/integration`

---

## 波次 A：文档重审（01–07）

| Task | 文档 | 源码重点 | 状态 |
| --- | --- | --- | --- |
| A1 | 01-bootstrap | `bootstrap/runtime.py`, `infra_core/settings.py` | pending |
| A2 | 02-contracts | `contracts/`, `skill_runtime/flow_executor.py`, `attempt_runner.py` | pending |
| A3 | 03-default-triage | `plugins/.../runner.py`, `flow_executor.py`, `apps/api` | pending |
| A4 | 04-skill-system | `skill_system/publisher.py` | pending |
| A5 | 05-skill-runtime | `skill_runtime/`, `flow_runtime/` | pending |
| A6 | 06-plugin | `plugin_system/`, `flow_plugin_id` | pending |
| A7 | 07-mcp-plane | `mcp_plane/`, `mcp_servers/` | pending |

## 波次 B：文档重审（08–14）

| Task | 文档 | 源码重点 | 状态 |
| --- | --- | --- | --- |
| B1 | 08-evidence-rca | `analysis/root_cause_engine.py`, `evidence_expander.py` | pending |
| B2 | 09-agent-runtime | `agent_runtime/`, `apps/*` 入口 | pending |
| B3 | 10-channel-routing | `channel_routing/webhook.py`, `apps/api` webhook | pending |
| B4 | 11-gateway | `gateway/`, `ws_bridge.py`, `apps/api` | pending |
| B5 | 12-task-runtime | `task_runtime/task_executor.py` | pending |
| B6 | 13-cron | `cron/scheduler.py`, `apps/scheduler` | pending |
| B7 | 14-code-index | `code_index/` | pending |

## 波次 C：文档重审（15–19 + 00）

| Task | 文档 | 状态 |
| --- | --- | --- |
| C1 | 15–17 storage/replay/approval | pending |
| C2 | 18-apps | pending |
| C3 | 19-observability | pending |
| C4 | 00-overview 汇总 | pending |

## 波次 D：Bug 修复（按链路优先级）

| ID | 链路 | 问题 | 状态 |
| --- | --- | --- | --- |
| D1 | Webhook | `ChannelSecurity` 未接入 | **done** — `ROOTSEEKER_WEBHOOK_*` + API 403 |
| D2 | Gateway HTTP | `case.create` 经 HTTP 无 WS flush（若存在） | N/A — case.create 主要为 WS；HTTP 无订阅方 |
| D3 | Docs | 清除 09/11/16 等过时「未接入」描述 | **done** — 01/02/09/10/11/16/00 |
| D4 | 全量测试 | `pytest tests/unit tests/integration` | **done** — 525 passed |

---

## 执行顺序

1. 波次 D 并行读代码确认 bug 列表（先于或穿插文档）
2. 波次 A→B→C 更新文档
3. 修复 D1–D3
4. D4 验证
