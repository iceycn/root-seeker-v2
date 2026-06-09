# T7 Agent 运行时内核

## 1. 任务目标

本任务用于把 OpenClaw Agent 代理核心模块中值得借鉴的运行时模型融入 RootSeeker V2。

RootSeeker V2 不应只把 Case 拆成普通步骤顺序执行，而应该有一个稳定的 Agent Runtime，负责管理：

- 主运行循环
- 单次 Attempt
- 工具调用循环
- 上下文构建与压缩
- 运行时服务
- Agent 事件

参考文档：

- `/Users/beisen/PycharmProjects/openclaw-analysis/05-Agent代理核心模块分析.md`

---

## 2. 范围

本任务覆盖：

- Agent Entry
- Runtime Services
- Run Loop
- Attempt Runner
- Tool Call Loop
- Context Compaction
- Agent Hooks
- Agent Events

本任务不覆盖：

- 具体 LLM Provider 接入细节
- 具体业务 Skill 内容
- UI 展示

---

## 3. 输入

- `CaseRecord`
- `CaseStep`
- `SkillExecutionPlan`
- `ToolCatalog`
- `EvidencePack`
- `RuntimeConfig`

---

## 4. 输出

- `AgentRunResult`
- `AttemptResult`
- `ToolExecutionTrace`
- `CompactedContext`
- `AgentEvent`

---

## 5. 一级拆解

### `T7.1` Agent Entry

定义 Agent 的入口结构，类似 OpenClaw `PiAgentEntry`。

### `T7.2` Run Loop

定义一次 Case 执行的主循环。

### `T7.3` Attempt Runner

定义单轮推理或单轮步骤执行。

### `T7.4` Tool Call Loop

统一承接模型或规则产生的工具调用。

### `T7.5` Context Compaction

为长 Case 和多轮排查提供上下文压缩。

---

## 6. 二级拆解

## 6.1 `T7.1` Agent Entry

### 建议字段

- `agent_id`
- `name`
- `config`
- `tools`
- `provider`
- `runtime_services`

### 类文件任务

- `agent_runtime/entry.py`
- `agent_runtime/runtime_services.py`

## 6.2 `T7.2` Run Loop

### 职责

- 加载 Case 上下文
- 获取下一步 Step
- 判断终止条件
- 调用 Attempt Runner
- 处理结果
- 发出生命周期事件

### 类文件任务

- `agent_runtime/run_loop.py`
- `agent_runtime/run_context.py`

## 6.3 `T7.3` Attempt Runner

### 职责

- 构建消息历史
- 构建 prompt
- 选择执行模式
- 支持 streaming / complete
- 汇总 AttemptResult

### 类文件任务

- `agent_runtime/attempt_runner.py`
- `agent_runtime/prompt_builder.py`
- `agent_runtime/model_router.py`

## 6.4 `T7.4` Tool Call Loop

### 职责

- 接收工具调用请求
- 交给 `mcp_plane`
- 收集工具结果
- 处理工具错误
- 写入执行轨迹

### 类文件任务

- `agent_runtime/tool_call_loop.py`
- `agent_runtime/tool_trace.py`

## 6.5 `T7.5` Context Compaction

### 职责

- 压缩长 Case 上下文
- 保留关键证据
- 剔除低价值工具输出
- 生成可复用摘要

### 类文件任务

- `agent_runtime/context_compactor.py`
- `agent_runtime/history_builder.py`

---

## 7. 风险

- 如果没有 Agent Runtime，后续 Case 执行会散落在 Supervisor、StepExecutor 和 Analysis 中
- 如果没有 Attempt 层，单次推理的输入输出无法稳定记录
- 如果没有上下文压缩，多轮排查会迅速超过上下文窗口

---

## 8. 验收标准

- Case 执行必须经过统一 Run Loop
- 每次 Attempt 必须有输入、输出、工具调用轨迹
- Agent Runtime 能发出生命周期、工具、错误、压缩事件
- Context Compaction 有明确触发条件和输出结构

---

## 9. 推荐实施顺序

1. 定义 `AgentEntry`
2. 定义 `RuntimeServices`
3. 实现 `RunLoop`
4. 实现 `AttemptRunner`
5. 接入 `ToolCallLoop`
6. 增加 `ContextCompactor`
