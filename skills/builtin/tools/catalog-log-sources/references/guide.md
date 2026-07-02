# 日志源解析

## 工具

- `catalog.get_log_sources`

## 输入

- `tenant`、`environment`、`service_name` 来自 `normalize-incident` 的 `case_request` / `extracted`。

## 前序步骤

- `normalize-incident`
- 建议在 `resolve-service` 之后执行
