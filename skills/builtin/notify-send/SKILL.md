---
name: notify-send
description: "在报告生成后发送排查结果通知。"
allowed-tools: notify.send
metadata:
  role: helper
---

# Notify send

报告生成后由 AttemptRunner 按已启用渠道自动调用 `notify.send`；playbook 规划阶段不要主动选择本工具。

详细准则见 `references/guide.md`。

## 参数线索

- `channel`: case metadata 的 `notify_channel`，默认 `webhook`
- `message`: 含服务名、标题、root_cause 标题、证据数量
