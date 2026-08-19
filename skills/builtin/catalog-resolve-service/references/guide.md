# 服务目录解析子技能

## 目标

把归整后的服务名映射到 RootSeeker 服务目录，获得日志源、仓库映射、负责人和允许工具等上下文。

## 工具

- `catalog.resolve_service`

## 执行准则

- 使用 `normalize-incident` 步骤输出的 `case_request` 中的 `service_name`、`tenant`、`environment`。
- 若归一化 metadata 含 tenant/environment，优先使用。
- 目录缺失时仍用原始服务名，记录限制说明。

## 前序步骤

- `normalize-incident` → `case_request`、`extracted`
