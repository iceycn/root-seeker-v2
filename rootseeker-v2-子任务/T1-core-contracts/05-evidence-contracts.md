# Evidence 契约

## 目标

定义证据、上下文窗口、假设、结论与报告。

## 输入

日志、trace、代码、指标、拓扑

## 输出

EvidencePack、ContextWindow、CaseReport

## 建议文件

- `contracts/evidence.py`
- `contracts/report.py`

## 具体步骤

- 定义 EvidenceType 与 EvidenceItem
- 定义 EvidencePack
- 定义 ContextWindow
- 定义 Hypothesis 与 RootCauseConclusion

## 验收标准

- Evidence 与 ContextWindow 分离
- ContextWindow 是预算治理后的结果

## 三级细化判断

结论：建议继续细化。

原因：该小目标仍包含多个动作或多个建议文件，继续拆分后更适合逐文件生成。

### 建议继续拆出的三级文档

- `01-定义-EvidenceType-与-EvidenceItem.md`：定义 EvidenceType 与 EvidenceItem
- `02-定义-EvidencePack.md`：定义 EvidencePack
- `03-定义-ContextWindow.md`：定义 ContextWindow
- `04-定义-Hypothesis-与-RootCauseConclusion.md`：定义 Hypothesis 与 RootCauseConclusion
- `05-contracts-evidence.py.md`：单独定义 ``contracts/evidence.py`` 的职责、输入输出和验收标准
- `06-contracts-report.py.md`：单独定义 ``contracts/report.py`` 的职责、输入输出和验收标准

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。
