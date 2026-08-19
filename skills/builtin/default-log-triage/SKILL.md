---
name: default-log-triage
description: "内置默认值班日志链路排查 Flow，按步骤加载工具 Skill 并生成参数。"
allowed-tools: incident.normalize catalog.resolve_service catalog.get_log_sources log.query_by_trace_id log.query_by_template trace.get_chain index.get_status repo.list code.search code.read graph.impact graph.context code.find_callers notify.send
metadata:
  role: playbook
---

# default-log-triage

用于 webhook 告警、replay 与人工错误排查。按下列 14 步推荐顺序执行；每步加载对应 helper Skill 文档，由 Agent 经 MCP Gateway 调用工具。不允许伪造结果。

## 推荐顺序（14 步）

1. `incident.normalize`（helper: `incident-normalize`）— 规整事件输入，提取服务、租户、环境、trace、症状、代码线索、`exception_summary` 与 `call_chain`
2. `catalog.resolve_service`（helper: `catalog-resolve-service`）— 将服务名映射到服务目录条目
3. `catalog.get_log_sources`（helper: `catalog-log-sources`）— 解析后续查询用的日志源
4. `log.query_by_trace_id`（helper: `log-query-trace`）— 按 trace id 拉取事发窗口日志
5. `log.query_by_template`（helper: `log-query-template`）— 按默认错误模板拉取兜底日志
6. `trace.get_chain`（helper: `trace-chain`）— 在有 trace id 时拉取分布式链路
7. `index.get_status`（helper: `index-repo-context`）— 读代码前确认索引是否可用
8. `repo.list`（helper: `index-repo-context`）— 目录或索引不完整时列出已注册仓库
9. `code.search`（helper: `code-lookup`）— 日志或 trace 给出具体线索后再搜代码
10. `code.read`（helper: `code-lookup`）— 读取命中文件或事件中的明确路径
11. `graph.impact`（helper: `graph-lookup`）— 对 `call_chain` 故障符号做 GitNexus 影响面
12. `graph.context`（helper: `graph-lookup`）— 加载故障方法的 360° 符号上下文
13. `code.find_callers`（helper: `code-lookup`）— 跨仓库追踪 caller（图谱优先，Zoekt 回退），与运行时调用链对齐
14. 生成报告之后再调用 `notify.send`（helper: `notify-send`）

生成报告之后再调用 notify.send。call notify.send after the report.

## AI 分析输入约定

错误排查工作台在生成 AI 分析时，不会上传完整 tool inputs/outputs 或整段堆栈，而是优先使用：

1. `normalize-incident` 提取的 `exception_summary` 与 `call_chain`
2. `graph-impact` / `graph-context`（GitNexus 影响面与符号上下文）
3. `find-callers`（`code.find_callers`，图谱优先 + Zoekt 回退）的 caller 对齐与 HTTP 入口
4. 规则引擎 report 摘要
5. 少量证据预览

因此 `incident.normalize` 必须尽量从原始日志中提取**业务调用链主方法**（如 `Controller -> Service -> Mapper`），供后续 AI 与 code/graph lookup 复用。

## 工具 Skill 索引

| 步骤 | 工具 Skill |
|------|------------|
| normalize | `incident-normalize` |
| catalog | `catalog-resolve-service`、`catalog-log-sources` |
| logs | `log-query-trace`、`log-query-template` |
| trace | `trace-chain` |
| index/repo | `index-repo-context` |
| code | `code-lookup` |
| graph | `graph-lookup` |
| notify | `notify-send` |

所有工具调用必须经过 MCP Gateway，不允许伪造结果。
