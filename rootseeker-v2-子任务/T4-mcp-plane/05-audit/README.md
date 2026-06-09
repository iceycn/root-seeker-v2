# Tool Audit 三级目标索引

父级文件：`05-audit.md`

## 三级文件列表

- `01-记录-request-id.md`：记录 request id（建议继续拆到四级）
- `02-记录-case-step-id.md`：记录 case/step id（建议继续拆到四级）
- `03-记录工具名.md`：记录工具名（建议继续拆到四级）
- `04-记录成功失败.md`：记录成功失败（建议继续拆到四级）
- `05-storage-audit_store.py.md`：单独定义 ``storage/audit_store.py`` 的职责、输入输出和验收标准（建议继续拆到四级）
- `06-contracts-audit.py.md`：单独定义 ``contracts/audit.py`` 的职责、输入输出和验收标准（建议继续拆到四级）

## 使用方式

后续实现时，优先一次只选择一个三级文件；若该三级文件标记为“建议继续拆到四级”，先按其中的四级建议再拆一层。
