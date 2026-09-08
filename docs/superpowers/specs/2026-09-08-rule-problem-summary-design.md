# 规则即时问题摘要（通知 + 错误排查页）

日期：2026-09-08  
状态：已批准（方案 A）  
范围：方案 A — 规则即时总结，不依赖 AI

## 背景

通知与错误排查页目前多以异常原文（如 `BusinessException: rpc interface error!`）作头条，缺少一句「这是什么问题」的可读总结。通知在报告生成后立即发送，此时 AI 分析通常尚未完成，因此总结必须由规则在报告时即时生成。

## 目标

1. 生成一句确定性的**问题摘要**（服务 + 故障点 + 异常简名/消息）。
2. 同一摘要用于：
   - 出站通知正文（`build_notify_args`）
   - 错误排查结果页（与证据摘要并列展示）
3. 不调用 LLM；无故障点/异常时优雅降级。

## 非目标

- 不等待 / 不二次发送 AI 分析通知
- 不扩展 `RootCauseConclusion` 契约字段（避免存储迁移）
- 不改通知渠道适配器协议

## 摘要生成规则

新增共用函数（建议 `rootseeker/analysis/problem_summary.py`）：

```text
build_problem_summary(*, symptom, service_name="", exception="", call_chain=None, max_chars=180) -> str
```

输入优先级：

1. `exception`（显式传入）否则从 `symptom` 提取 `extract_exception_summary`
2. 故障点：`call_chain[0]`，否则从 `symptom` 提取 `extract_call_chain_summary` 首帧，再规整为 `Class.method`（去掉文件行号括号）
3. `service_name`（占位名则忽略）

输出模板（有缺项则省略对应片段）：

```text
{service} 在 {fault} 抛出 {exception_short}
```

示例：

```text
knowledge-api-service 在 CourseWorkflowMessageListener.sendCourseApprovalOAMessage 抛出 BusinessException: rpc interface error!
```

仅有异常时：`抛出 BusinessException: ...`  
仅有故障点时：`在 Xxx.yyy 出现错误`  
皆无时：返回空字符串（调用方回退现有 headline）。

## 通知正文

`_build_notify_message` 调整为：

```text
【RootSeeker】{headline}          # 仍优先异常原文，便于扫一眼
问题：{problem_summary}           # 新增；与 headline 重复则跳过
服务：...
结论：...                         # 仅当与问题摘要/headline 不重复
说明：...                         # 继续过滤过程话术
置信度：...
Case：...
```

## 报告与错误排查页

1. `build_case_report`：`CaseReport.summary` 优先设为 `problem_summary`；若为空则保留现有证据计数英文摘要（或中文等价）。
2. Admin `POST/GET /api/error-chat` 响应增加 `problem_summary`（从 `report.summary` 或现场用同一 helper 生成，保证与通知一致）。
3. 错误排查结果卡增加一行 **问题摘要**（在证据摘要之上）；证据摘要语义不变。

## 测试

- 单测：`build_problem_summary` 完整 / 缺服务 / 缺故障点 / 占位服务名
- 单测：`build_notify_args` 含 `问题：` 且与异常 headline 不重复堆砌
- 单测：`build_case_report` 的 `summary` 为问题摘要而非仅 `Collected N evidence`

## 验收

用既有 `knowledge-api` / `BusinessException` 样例排查后：

- 飞书/Webhook 消息含「问题：…sendCourseApprovalOAMessage…BusinessException…」
- Admin 错误排查页可见同一句问题摘要
- 通知仍在报告后即时发出，不依赖 AI
