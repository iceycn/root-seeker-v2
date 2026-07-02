# 输入归整子技能

## 目标

把原始告警载荷规整成默认排查流程统一使用的事件字段。后续所有步骤应优先使用本步骤输出，不直接猜测原始 payload。

## 触发时机

- 默认 flow 的第一步。
- webhook、replay、页面错误排查提交都必须先执行。

## 工具

- `incident.normalize`

## 输入线索

- 服务名：`service_name`、`service`、Prometheus label、SLS project 等。
- 租户和环境：`tenant`、`environment`。
- Trace：`trace_id`、`traceId`、日志/症状文本中的 trace 片段。
- 症状：`message`、`description`、`alert_name`、异常摘要。
- 时间窗口：`start_time`、`end_time`、告警触发时间。
- 代码线索：`code_path`、`code_symbol`、`Foo.java:42` 这类文本。

## 输出要求

- 输出 `case_request`，供后续步骤统一使用。
- 输出 `extracted`，包含服务、租户、环境、trace、症状、来源、严重级别、时间窗口、代码路径、代码符号。
- 输出 `missing_fields`，明确哪些关键字段缺失。
- 缺失字段只代表未知输入，不能作为系统健康或无故障的证据。

## 前序步骤上下文

- 本步骤通常无前序输出；使用原始 `case` 字段构造 `payload`。
