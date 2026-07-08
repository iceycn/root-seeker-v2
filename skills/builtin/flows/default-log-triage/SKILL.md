---
name: Default log triage
description: "内置默认值班日志链路排查 Flow，按步骤加载工具 Skill 并生成参数。"
---

# Default log triage

用于 webhook 告警、replay 与人工错误排查。按 `rootseeker-skill.yaml` 中的步骤顺序执行；每步加载对应 **工具 Skill** 文档，由 LLM 生成 MCP 工具参数。

## AI 分析输入约定

错误排查工作台在生成 AI 分析时，不会上传完整 tool inputs/outputs 或整段堆栈，而是优先使用：

1. `normalize-incident` 提取的 `exception_summary` 与 `call_chain`
2. `find-callers`（`code.find_callers`）的 caller 对齐与 HTTP 入口（供 AI `caller_trace`）
3. 规则引擎 report 摘要
4. 少量证据预览

因此 `incident.normalize` 必须尽量从原始日志中提取**业务调用链主方法**（如 `Controller -> Service -> Mapper`），供后续 AI 与 code lookup 复用。

## 工具 Skill 索引

| 步骤 | 工具 Skill |
|------|------------|
| normalize | `tools/incident-normalize` |
| catalog | `tools/catalog-resolve-service`、`tools/catalog-log-sources` |
| logs | `tools/log-query-trace`、`tools/log-query-template` |
| trace | `tools/trace-chain` |
| index/repo | `tools/index-repo-context` |
| code | `tools/code-lookup` |
| notify | `tools/notify-send` |

所有工具调用必须经过 MCP Gateway，不允许伪造结果。
