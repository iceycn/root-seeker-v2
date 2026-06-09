# T14 Task 与 Flow 运行时

## 1. 目标

本任务用于统一 RootSeeker V2 中 Case 执行、Flow 执行、定时执行、回放执行的任务模型，避免执行逻辑分散在 `T2`、`T7`、`T8`、`T12` 中。

## 2. 范围

覆盖：

- Task 契约
- Flow 契约
- TaskExecutor
- FlowExecutor
- Checkpoint
- Revision
- Queue
- Run Trace

不覆盖：

- 具体日志查询逻辑
- 具体 Skill 生成逻辑
- 具体 UI 展示

## 3. 强制约束

- Flow 的每一步必须来自 Skill Step 或 Flow Plugin 声明。
- Task 执行不得直接调用 Provider、Adapter 或 SDK。
- Task 执行工具必须走 MCP。
- Flow 执行过程必须生成 `CaseExecutionTrace`。

## 4. 核心对象

- `TaskRecord`
- `TaskStatus`
- `FlowSpec`
- `FlowStep`
- `FlowRun`
- `Checkpoint`
- `CaseExecutionTrace`
- `SkillExecutionTrace`

## 5. 推荐文件

- `task_runtime/task.py`
- `task_runtime/task_queue.py`
- `task_runtime/task_executor.py`
- `task_runtime/task_store.py`
- `flow_runtime/flow_contract.py`
- `flow_runtime/flow_executor.py`
- `flow_runtime/checkpoint.py`
- `flow_runtime/run_trace.py`

## 6. 与其它任务关系

- `T2` 使用 Task Runtime 跑最小链路。
- `T7` Agent Runtime 作为 Task 的执行策略之一。
- `T8` Flow Plugin 输出 `FlowSpec`。
- `T12` Cron 触发 Task。
- `T18` Replay 通过 Task Runtime 执行回放。

## 7. 验收标准

- Case 执行、默认 Flow、Cron、Replay 都能映射到统一 Task。
- Task 状态可查询、可恢复、可审计。
- Flow 每一步都有输入、输出、状态和 trace。
- 任意工具调用都能追溯到 `Case -> Skill -> Step -> Plugin Capability -> MCP ToolCall`。
