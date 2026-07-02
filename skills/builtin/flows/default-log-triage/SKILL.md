---
name: Default log triage
description: "内置默认值班日志链路排查 Flow，按步骤加载工具 Skill 并生成参数。"
---

# Default log triage

用于 webhook 告警、replay 与人工错误排查。按 `rootseeker-skill.yaml` 中的步骤顺序执行；每步加载对应 **工具 Skill** 文档，由 LLM 生成 MCP 工具参数。

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
