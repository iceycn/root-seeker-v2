# T12 Cron 定时任务

## 1. 任务目标

本任务用于借鉴 OpenClaw Cron 定时任务系统，为 RootSeeker V2 建立企业级调度能力。

企业级故障排查系统必然需要定时任务，包括：

- 定时巡检
- 定时索引刷新
- 定时同步配置
- 定时回放故障样本
- 定时评估 Skill 效果
- 定时健康检查

参考文档：

- `/Users/beisen/PycharmProjects/openclaw-analysis/cron/01-cron-scheduling-system.ts.md`
- `/Users/beisen/PycharmProjects/openclaw-analysis/cron/01-cron-service.ts.md`

---

## 2. 范围

本任务覆盖：

- Cron Job 契约
- Cron 表达式解析
- 调度器
- 确定性错峰
- 并发控制
- 重试策略
- 状态持久化

本任务不覆盖：

- 分布式调度集群的完整实现
- 复杂工作流编排

---

## 3. 输入

- Cron 配置
- Job 定义
- 当前时间
- 运行状态

---

## 4. 输出

- `CronJobState`
- `NextRunAt`
- `JobRunResult`
- `CronEvent`

---

## 5. 一级拆解

### `T12.1` Cron Job 契约

定义定时任务结构。

### `T12.2` 调度算法

解析表达式并计算下一次运行时间。

### `T12.3` 错峰与并发

避免大量任务同时触发。

### `T12.4` 失败恢复

处理重试、陈旧运行标记和状态恢复。

---

## 6. 二级拆解

## 6.1 `T12.1` Cron Job 契约

### 字段建议

- `job_id`
- `name`
- `schedule`
- `timezone`
- `enabled`
- `max_concurrent_runs`
- `retry_policy`
- `state`

### 类文件任务

- `cron/contracts.py`
- `cron/job.py`

## 6.2 `T12.2` 调度算法

### 职责

- Cron 表达式解析
- 表达式缓存
- 下一次运行时间计算

### 类文件任务

- `cron/schedule.py`
- `cron/scheduler.py`

## 6.3 `T12.3` 错峰与并发

### 职责

- 基于 `job_id` 计算稳定偏移
- 限制最大并发
- 防止同类任务集中启动

### 类文件任务

- `cron/stagger.py`
- `cron/concurrency.py`

## 6.4 `T12.4` 失败恢复

### 职责

- 指数退避
- 失败次数记录
- 清理陈旧 running 标记
- 调度状态持久化

### 类文件任务

- `cron/retry.py`
- `cron/state_store.py`
- `cron/recovery.py`

---

## 7. 风险

- 如果没有错峰，企业环境中多个巡检任务会同时打爆外部平台
- 如果没有陈旧任务清理，进程重启后任务状态会卡住
- 如果没有状态持久化，任务历史和失败原因无法追踪

---

## 8. 验收标准

- 能注册定时任务
- 能计算下一次运行时间
- 能限制并发
- 能进行错峰
- 能处理失败重试
- 能恢复陈旧运行状态

---

## 9. 推荐实施顺序

1. 定义 CronJob
2. 实现表达式解析
3. 实现调度器
4. 实现错峰
5. 实现重试和状态恢复
