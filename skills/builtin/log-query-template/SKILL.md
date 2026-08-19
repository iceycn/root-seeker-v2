---
name: log-query-template
description: "按默认错误模板查询日志作为兜底证据。"
allowed-tools: log.query_by_template
metadata:
  role: helper
---

# Log query by template

调用 `log.query_by_template`，`template_id` 固定为 `default.error_window`。

详细准则见 `references/guide.md`。
