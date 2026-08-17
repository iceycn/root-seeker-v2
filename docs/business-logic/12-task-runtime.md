# 统一任务运行时（Task Runtime）

## 1. 业务目标

RootSeeker V2 将「异步执行单元」统一抽象为 `TaskRecord`，由 `TaskRuntime` 负责提交、排队与单次调度。调用方（Worker、Scheduler、CLI 等）只需 `submit(kind, payload)`，无需各自实现队列与状态持久化。

`TaskKind` 覆盖五类业务动作：`CASE_RUN`（完整默认排查流）、`FLOW_RESUME`（从 checkpoint 恢复或重放）、`FLOW_STEP`（从指定步骤索引单步续跑）、`CRON` / `REPLAY`（回放套件 + 部署门禁评估）。成功时任务状态为 `completed`，`result_ref` 指向 case_id、flow_run_id 或 replay report_id；失败时状态为 `failed` 或异常向上抛出，错误写入 `task.error`。

内存队列 `TaskQueue` 保证同进程 FIFO；持久化 Store（sqlite/mysql）使 Worker 重启后仍可通过 `_next_pending_task_id` 捞取 pending 任务。任务本身不直接写 Case/Evidence/Report，而是通过 `TaskExecutor` 委托 `FlowRuntime`、`FlowExecutor` 或 `ReplayRunner` 完成实际业务副作用。

## 2. 入口一览

| 入口类型 | 路径 / 符号 | 说明 |
| --- | --- | --- |
| Worker 单次 | `apps/worker/main.py:run_once` | 创建 `TaskRuntime`，可选 seed demo 后 `run_once()` |
| Worker 循环 | `apps/worker/main.py:run_loop` | 轮询 `run_once()`，空队列达 `max_empty_polls` 或达 `max_runs` 退出 |
| Scheduler 定时回放 | `apps/scheduler/main.py`（`replay.default_flow` handler） | `submit(CRON)` + 同步 `run_once()`，读 `report_gate_passed` / `report_release_allowed` 判定 Job 成败 |
| CLI 恢复 | `apps/cli/main.py:_run_resume` | `submit(FLOW_RESUME)` + `run_once()` |
| 编排门面 | `rootseeker/task_runtime/runtime.py:TaskRuntime` | `submit` / `run_once` 对外统一 API |
| 执行器 | `rootseeker/task_runtime/task_executor.py:TaskExecutor.execute` | 按 `TaskKind` 分派到 Flow / Replay |
| 单元测试 | `tests/unit/task_runtime/` | 直接构造 `TaskRuntime` / `TaskExecutor` 验证各 kind |

说明：`CASE_RUN` 的生产入口目前主要是 Worker demo seed 与测试；API/Gateway 侧默认排查链路见 [03-default-triage-flow.md](./03-default-triage-flow.md)，不一定经 Task 层。`TaskKind.REPLAY` 在契约与执行器中与 `CRON` 共用分支，**未在代码中找到**独立的 `submit(kind=REPLAY)` 调用点。

## 3. 主调用链（逐步）

### 3.1 提交与调度总览

```mermaid
sequenceDiagram
    participant Caller as 调用方
    participant TR as TaskRuntime
    participant Create as create_task_record
    participant Store as TaskStore/Sqlite/Mysql
    participant Q as TaskQueue
    participant EX as TaskExecutor

    Caller->>TR: submit(kind, payload, case_id?)
    TR->>Create: create_task_record(...)
    Create-->>TR: TaskRecord(status=PENDING)
    TR->>Store: save(task)
    TR->>Q: push(task_id)
    TR-->>Caller: TaskRecord

    Caller->>TR: run_once()
    TR->>Q: pop() 或 _next_pending_task_id(store)
    alt 无待执行任务
        TR-->>Caller: None
    else 有 task_id
        TR->>EX: execute(task_id)
        EX->>Store: get → RUNNING → save
        EX->>EX: 按 kind 分派
        EX->>Store: COMPLETED/FAILED → save
        TR->>Store: get(task_id)
        TR-->>Caller: TaskRecord
    end
```

1. `rootseeker/task_runtime/runtime.py` → `TaskRuntime.submit`
   - 入：`kind: TaskKind`，`payload: dict`，可选 `case_id: str | None`
   - 出：持久化后的 `TaskRecord`（初始 `status=PENDING`）
   - 下一步：`create_task_record` → `store.save` → `queue.push`

2. `rootseeker/task_runtime/task.py` → `create_task_record`
   - 入：同上
   - 出：`TaskRecord(task_id=new_id("task-"), kind, case_id, payload)`，默认 `status=PENDING`
   - 下一步：返回 `TaskRuntime.submit`

3. `rootseeker/task_runtime/task_store.py`（或 sqlite/mysql 实现）→ `save`
   - 入：完整 `TaskRecord`
   - 出：无（覆盖写入）
   - 下一步：`TaskQueue.push`

4. `rootseeker/task_runtime/task_queue.py` → `TaskQueue.push`
   - 入：`task_id: str`
   - 出：无（`deque` 尾部追加）
   - 下一步：等待 `run_once`

5. `rootseeker/task_runtime/runtime.py` → `TaskRuntime.run_once`
   - 入：无
   - 出：`TaskRecord | None`（执行后的最新记录）
   - 逻辑：`task_id = queue.pop()`；若为空则 `_next_pending_task_id(store)` 按 `created_at` 取最早 pending
   - 下一步：`TaskExecutor.execute(task_id)`

6. `rootseeker/task_runtime/task_executor.py` → `TaskExecutor.execute`
   - 入：`task_id: str`
   - 出：无（副作用写入 store）
   - 逻辑：`get` → `status=RUNNING` → `save` → 按 `kind` 分支 → 终态 `save`
   - 下一步：各 kind 具体 handler（见 §3.2）

### 3.2 按 TaskKind 的执行分派

| TaskKind | 调用函数 | 主要输入（payload） | 成功时 result_ref / payload 补充 |
| --- | --- | --- | --- |
| `CASE_RUN` | `FlowRuntime.run_default(req)` | `CaseCreateRequest` 字段平铺在 payload | `result_ref=case_id`；`payload["flow_run_id"]=trace.execution_id` |
| `FLOW_RESUME` | `FlowRuntime.resume_default(flow_run_id, case_request, force)` | `flow_run_id`，`case_request`，`force` | 已完成则 `resume_status=skipped_completed`；否则 `result_ref=case_id`，`resume_status` 来自 checkpoint |
| `FLOW_STEP` | `FlowExecutor.execute_from_checkpoint(...)` | `flow_run_id`，`step_index`，`case_request` | `result_ref=case_id`；`payload["executed_step_index"]` |
| `CRON` / `REPLAY` | `ReplayRunner.run_suite` + `DeploymentPolicyOrchestrator.evaluate` | `suite_name`（默认 `cron-default-flow`），`repeat_each`（默认 1） | `result_ref=report_id`；`report_*`、`deployment_decision` 写入 payload |

分派代码锚点（节选）：

```python
# rootseeker/task_runtime/task_executor.py
if task.kind == TaskKind.CASE_RUN:
    res = self._flow_runtime.run_default(CaseCreateRequest.model_validate(task.payload))
elif task.kind == TaskKind.FLOW_RESUME:
    resumed = self._flow_runtime.resume_default(...)
elif task.kind == TaskKind.FLOW_STEP:
    result = FlowExecutor(self._runtime).execute_from_checkpoint(...)
elif task.kind in {TaskKind.CRON, TaskKind.REPLAY}:
    result = ReplayRunner(...).run_suite(...)
    decision = DeploymentPolicyOrchestrator(...).evaluate(result.report)
else:
    task.status = TaskStatus.FAILED  # unsupported kind
```

### 3.3 Worker 进程如何使用 TaskRuntime

1. `apps/worker/main.py` → `run_once` / `run_loop`
   - `runtime = create_dev_runtime(repo_root)`（见 [01-bootstrap-wiring.md](./01-bootstrap-wiring.md)）
   - `task_runtime = TaskRuntime(runtime)` — 按 `ROOTSEEKER_STORAGE_BACKEND` 自动选择 Task Store
   - 可选 `_seed_demo_task`：`submit(CASE_RUN, {...})`
   - 循环体：`task = task_runtime.run_once()`；`None` 时递增 `empty_polls` 并 `sleep(interval_seconds)`；非 `completed` 时 `run_loop` 返回退出码 1

2. `apps/scheduler/main.py`（`replay.default_flow` 分支）
   - 同步模式：`submit(CRON)` 后立即 `run_once()`，不依赖独立 Worker 进程
   - Job 成败由 `executed.status` 与 `report_release_allowed` 共同决定（详见 [13-cron-scheduler.md](./13-cron-scheduler.md)）

3. `apps/cli/main.py` → `_run_resume`
   - `submit(FLOW_RESUME, {flow_run_id, case_request, force})` → `run_once()` → 打印 `resume_status`

### 3.4 Store 后端选择链

1. `TaskRuntime.__init__` 未传入 `store` 时调用 `_build_default_task_store(runtime)`
2. 读取 `RootSeekerSettings().storage_backend`（环境变量 `ROOTSEEKER_STORAGE_BACKEND`，默认 `memory`）
3. 分支：
   - `mysql` → `MysqlTaskStore(mysql_config_from_settings(settings))` — `rootseeker/storage/mysql_task.py`
   - `sqlite` → `SqliteTaskStore(db_path)`，相对路径相对 `runtime.repo_root` — `rootseeker/storage/sqlite_task.py`
   - 其他 / `memory` → 进程内 `TaskStore()` — `rootseeker/task_runtime/task_store.py`

持久化 Store 实现 `list_by_status`，供 `_next_pending_task_id` 在队列为空时恢复 pending 任务（跨 Worker 实例场景见 `tests/unit/test_bootstrap_storage.py`）。

## 4. 关键数据结构

定义于 `rootseeker/contracts/task.py`：

| 类型 | 字段 / 取值 | 谁填充 | 谁消费 |
| --- | --- | --- | --- |
| `TaskKind` | `case_run` / `flow_resume` / `flow_step` / `cron` / `replay` | `submit` 调用方 | `TaskExecutor.execute` 分派 |
| `TaskStatus` | `pending` → `running` → `completed` \| `failed` \| `cancelled` | `create_task_record` 初始 pending；executor 写 running/终态 | Worker/Scheduler 读终态；Store 索引 |
| `TaskRecord` | `task_id`, `kind`, `case_id?`, `flow_id?`, `skill_slug?`, `status`, `payload`, `result_ref?`, `error?`, `created_at`, `updated_at` | `create_task_record` + executor 回写 | Store 全字段持久化 |

`CASE_RUN` payload 需满足 `CaseCreateRequest`（`rootseeker/contracts/case.py`）。`FLOW_RESUME` / `FLOW_STEP` 额外要求 `flow_run_id` 与嵌套 `case_request` dict。

`TaskQueue`（`rootseeker/task_runtime/task_queue.py`）仅保存 `task_id` 字符串队列，不持久化；进程重启后依赖 Store 的 pending 列表兜底。

## 5. 状态与副作用

### Task 状态变迁

| 阶段 | status | 触发位置 |
| --- | --- | --- |
| 创建 | `pending` | `create_task_record` 默认值 |
| 开始执行 | `running` | `TaskExecutor.execute` 开头 |
| 成功 | `completed` | 各 kind 分支正常返回 |
| 失败 | `failed` | `FLOW_STEP` checkpoint 缺失；未知 kind |
| 未使用 | `cancelled` | 契约存在，**未在代码中找到**写入点 |

### 各 kind 的下游副作用（经委托层）

| TaskKind | 间接写入的 Store / 产物 |
| --- | --- |
| `CASE_RUN` | 经 `FlowRuntime.run_default` → Case / Evidence / Report / Checkpoint（见 [03-default-triage-flow.md](./03-default-triage-flow.md)） |
| `FLOW_RESUME` | 经 `FlowRuntime.resume_default` → 可能续跑步骤或跳过；读 `flow_checkpoint_store` |
| `FLOW_STEP` | 经 `FlowExecutor.execute_from_checkpoint` → 从指定 index 执行剩余步骤 |
| `CRON` / `REPLAY` | `ReplayRunner` 写 replay 报告；`DeploymentPolicyOrchestrator` 读 approval 策略（见 [17-approval-governance-replay.md](./17-approval-governance-replay.md)） |

Task Store 本身只存 `TaskRecord` JSON 行，不存 Case 正文。

## 6. 分支与错误

| 条件 | 代码位置 | 行为 |
| --- | --- | --- |
| `task_id` 不存在 | `task_executor.py:execute` | 抛出 `ValueError("task not found: ...")` |
| `FLOW_RESUME` 缺 `flow_run_id` | 同上 | 抛出 `ValueError` |
| `FLOW_STEP` 缺 `flow_run_id` | 同上 | 抛出 `ValueError` |
| `FLOW_STEP` checkpoint 不存在 | 同上 | `status=FAILED`，`error={"reason": "checkpoint not found: ..."}` |
| 未知 / 未实现 kind | 同上 | `status=FAILED`，`error={"reason": "unsupported kind: ..."}` |
| `queue.pop()` 为空但 Store 有 pending | `runtime.py:_next_pending_task_id` | 取 `created_at` 最早的一条 pending 执行（跨实例恢复） |
| `run_once` 无任务 | `runtime.py:run_once` | 返回 `None`；Worker `run_once` 退出码 1 |
| Scheduler CRON 任务未 completed 或门禁未放行 | `apps/scheduler/main.py` | `JobRunStatus.FAILED` |
| Flow/Replay 内部异常 | `TaskExecutor.execute` 各分支 | **未捕获**，向上传播；Task 可能停留在 `running`（取决于异常抛出点） |

`FLOW_RESUME` 当目标 flow 已完成且 `force=False` 时，`resume_default` 返回 `None`，任务仍标记 `completed`，`payload["resume_status"]="skipped_completed"`。

## 7. 相关测试

| 测试文件 | 覆盖点 |
| --- | --- |
| `tests/unit/task_runtime/test_task_runtime.py` | `TaskQueue` FIFO；`TaskExecutor` 对 `CASE_RUN` / `CRON` / `FLOW_RESUME` / `FLOW_STEP` 的端到端执行与 payload 断言 |
| `tests/unit/task_runtime/test_task_runtime_orchestrator.py` | `TaskRuntime.submit` + `run_once` 编排；`FLOW_RESUME` 在 `force=True` 时 `resume_status` 为 `resumed_from_step` 或 `replayed` |
| `tests/unit/test_bootstrap_storage.py` | sqlite 后端下 submit 与 run 跨两个 `TaskRuntime` 实例，验证 pending 任务持久化与执行 |
| `tests/unit/storage/test_sqlite_store.py` | `SqliteTaskStore` CRUD 与 `list_all` |
| `tests/unit/apps/test_worker_main.py` | Worker CLI 参数与 `run_once` / `run_loop` 行为（mock `TaskRuntime`） |
| `tests/unit/apps/test_scheduler_main.py` | Scheduler `replay.default_flow` 路径 mock `TaskRuntime` |
| `tests/integration/test_e2e_full_chain.py` | 全链路中含 Task 持久化断言 |

注：`docs/business-logic/01-bootstrap-wiring.md` 提及的 `tests/unit/task_runtime/test_task_executor.py` **未在仓库中找到**；executor 覆盖集中在 `test_task_runtime.py`。

## 8. 与其他文档的关系

| 文档 | 关系 |
| --- | --- |
| [03-default-triage-flow.md](./03-default-triage-flow.md) | `CASE_RUN` 经 `FlowRuntime.run_default` 进入默认排查主链路 |
| [05-skill-runtime-flow-executor.md](./05-skill-runtime-flow-executor.md) | `FLOW_RESUME` / `FLOW_STEP` 依赖 Flow checkpoint 与 `FlowExecutor.execute_from_checkpoint` |
| [13-cron-scheduler.md](./13-cron-scheduler.md) | Scheduler 如何注册 `replay.default_flow` Job 并同步调用 `TaskRuntime` |
| [17-approval-governance-replay.md](./17-approval-governance-replay.md) | `CRON`/`REPLAY` 任务执行后 `DeploymentPolicyOrchestrator.evaluate` 与 `report_release_allowed` |
| [01-bootstrap-wiring.md](./01-bootstrap-wiring.md) | `create_dev_runtime` 与 `ROOTSEEKER_STORAGE_BACKEND` 如何影响默认 Task Store |
| [02-contracts-state-machines.md](./02-contracts-state-machines.md) | `TaskKind` / `TaskStatus` / `TaskRecord` 契约定义 |
| [16-storage.md](./16-storage.md) | `SqliteTaskStore` / `MysqlTaskStore` 表结构与读写细节（本篇仅述选择逻辑） |
| [18-apps-api-admin-cli.md](./18-apps-api-admin-cli.md) | Worker / Scheduler / CLI 进程入口汇总 |

---

## 附录：模块职责速查

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| 门面 | `rootseeker/task_runtime/runtime.py` | `TaskRuntime`：`submit`、`run_once`、默认 Store 工厂 |
| 工厂 | `rootseeker/task_runtime/task.py` | `create_task_record` |
| 队列 | `rootseeker/task_runtime/task_queue.py` | 内存 FIFO `task_id` |
| 内存存储 | `rootseeker/task_runtime/task_store.py` | 字典 `TaskStore` |
| 执行 | `rootseeker/task_runtime/task_executor.py` | `TaskExecutor` 五类 kind 分派 |
| 契约 | `rootseeker/contracts/task.py` | `TaskKind`, `TaskStatus`, `TaskRecord` |
| SQLite | `rootseeker/storage/sqlite_task.py` | 持久化 + `list_by_status` |
| MySQL | `rootseeker/storage/mysql_task.py` | 同上，MySQL 方言 |
