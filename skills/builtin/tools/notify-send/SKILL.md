---
name: Notify send
description: "在报告生成后发送排查结果通知。"
---

# Notify send

调用 `notify.send`。必须在 `build_case_report` 之后执行（`defer_until: after_report`）。

详细准则见 `references/guide.md`。

## 参数线索

- `channel`: case metadata 的 `notify_channel`，默认 `webhook`
- `message`: 含服务名、标题、root_cause 标题、证据数量
