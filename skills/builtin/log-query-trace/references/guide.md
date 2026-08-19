# 日志查询 — trace

## 工具

- `log.query_by_trace_id`

## 参数线索

- `trace_id`：来自 `normalize-incident` 的 `extracted.trace_id` 或 case metadata，缺省可用 `trace-unknown`。
- `service_name`：归一化后的服务名。

## 前序步骤

- `normalize-incident` 必须已完成。
