# 调用默认 Tool

## 上级目标

- 父级任务：`T2-bootstrap-skeleton`
- 父级小目标：`06-minimal-chain.md`
- 父级标题：最小链路

## 三级目标

调用默认 Tool

## 输入

CaseCreateRequest

## 输出

CaseReport

## 建议落地文件

- `supervisor/case_supervisor.py`
- `step_engine/step_executor.py`

## 四级细化判断

结论：建议继续拆到四级。

原因：该三级目标仍包含可独立设计、实现或测试的子步骤，继续拆到四级更适合后续逐文件生成。

### 建议继续拆出的四级文档

- `01-request-model.md`：请求模型与参数映射
- `02-execution-path.md`：执行路径与超时控制
- `03-error-handling.md`：错误处理与重试
- `04-audit-tests.md`：审计与测试点
- `05-file-boundaries.md`：多文件职责边界

## 停止继续拆分的条件

- 只对应一个类、一个函数入口、一个 DTO 或一个 schema 片段。
- 实现时预计只改 1 个文件，且测试点不超过 3 个。
- 输入、输出和失败模式已经可以被一句话说明。

## 验收标准

- 能直接映射父级小目标的验收标准。
- 能明确目标文件、输入对象、输出对象和至少一个测试点。
