# 构建 prompt

## 上级目标

- 父级任务：`T7-agent-runtime`
- 父级小目标：`05-attempt-runner.md`
- 父级标题：Attempt Runner

## 三级目标

构建 prompt

## 输入

message、context

## 输出

AttemptResult

## 建议落地文件

- `agent_runtime/attempt_runner.py`

## 四级细化判断

结论：建议继续拆到四级。

原因：该三级目标仍包含可独立设计、实现或测试的子步骤，继续拆到四级更适合后续逐文件生成。

### 建议继续拆出的四级文档

- `01-input-shape.md`：输入结构与前置条件
- `02-builder-logic.md`：构建逻辑与分支
- `03-output-shape.md`：输出结构与后置条件
- `04-tests.md`：测试样例与失败场景

## 停止继续拆分的条件

- 只对应一个类、一个函数入口、一个 DTO 或一个 schema 片段。
- 实现时预计只改 1 个文件，且测试点不超过 3 个。
- 输入、输出和失败模式已经可以被一句话说明。

## 验收标准

- 能直接映射父级小目标的验收标准。
- 能明确目标文件、输入对象、输出对象和至少一个测试点。
