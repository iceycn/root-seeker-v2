# 最小链路

## 目标

打通创建 Case 到生成报告的闭环。

## 输入

CaseCreateRequest

## 输出

CaseReport

## 建议文件

- `supervisor/case_supervisor.py`
- `step_engine/step_executor.py`

## 具体步骤

- 创建 Case
- 选择默认 Skill
- 生成 Step
- 调用默认 Tool
- 生成报告

## 验收标准

- 最小链路能在测试中闭环

## 三级细化判断

结论：建议继续细化。

原因：该小目标仍包含多个动作或多个建议文件，继续拆分后更适合逐文件生成。

### 建议继续拆出的三级文档

- `01-创建-Case.md`：创建 Case
- `02-选择默认-Skill.md`：选择默认 Skill
- `03-生成-Step.md`：生成 Step
- `04-调用默认-Tool.md`：调用默认 Tool
- `05-生成报告.md`：生成报告
- `06-supervisor-case_supervisor.py.md`：单独定义 ``supervisor/case_supervisor.py`` 的职责、输入输出和验收标准
- `07-step_engine-step_executor.py.md`：单独定义 ``step_engine/step_executor.py`` 的职责、输入输出和验收标准

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。
