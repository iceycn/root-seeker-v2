---
name: Incident normalize
description: "将原始告警载荷规整为统一事件字段，供后续排查步骤使用。"
---

# Incident normalize

调用 `incident.normalize` 把 webhook、replay 或页面提交的原始载荷规整为 `case_request` 与 `extracted` 字段。

详细准则见 `references/guide.md`。

## 参数线索

- 输入来自原始 Case：`title`、`service_name`、`symptom`（message）、`source`、`metadata`。
- 将 metadata 与上述字段合并为 `payload` 传给工具。

## 输出

- `case_request`：后续步骤统一使用的归一化 Case。
- `extracted`：服务、租户、环境、trace、症状、代码路径，以及 `exception_summary` / `call_chain`（调用链主方法）。
- `missing_fields`：缺失字段列表（不代表系统健康）。
