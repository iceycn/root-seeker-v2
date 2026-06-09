# Case 契约

## 目标

定义 Case、Step、状态机与计划快照。

## 输入

用户请求、告警事件、回放请求

## 输出

CaseRecord、CaseStep、CasePlanSnapshot

## 建议文件

- `contracts/case.py`

## 具体步骤

- 定义 CaseCreateRequest
- 定义 CaseStatus 与 StepStatus
- 定义 CaseRecord 与 CaseStep
- 定义 CasePlanSnapshot

## 验收标准

- Case 与 Step 边界清晰
- Tool 层不能直接修改 Case 顶层状态

## 三级细化判断

结论：建议继续细化。

原因：该小目标仍包含多个动作或多个建议文件，继续拆分后更适合逐文件生成。

### 建议继续拆出的三级文档

- `01-定义-CaseCreateRequest.md`：定义 CaseCreateRequest
- `02-定义-CaseStatus-与-StepStatus.md`：定义 CaseStatus 与 StepStatus
- `03-定义-CaseRecord-与-CaseStep.md`：定义 CaseRecord 与 CaseStep
- `04-定义-CasePlanSnapshot.md`：定义 CasePlanSnapshot

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。