# Root Cause Engine

## 目标

生成和验证根因假设。

强制边界：

- RootCauseEngine 只能消费 `EvidencePack` 或由其裁剪得到的 `ContextWindow`。
- RootCauseEngine 不能直接触发日志查询、服务目录解析、trace 查询、代码搜索或 LSP 查询。
- 如果缺少证据，RootCauseEngine 只能返回“证据不足”的假设或请求上游补证，不能自行调用 MCP。
- 所有工具调用必须发生在 `Skill Step -> Plugin Capability -> MCP ToolCall` 链路中。

## 输入

ContextWindow

## 输出

HypothesisSet、Conclusion

## 建议文件

- `analysis/root_cause_engine.py`

## 具体步骤

- 提出多个假设
- 关联支持证据
- 给出置信度
- 收敛结论

## 验收标准

- 假设和最终结论分离
- RootCauseEngine 不直接依赖任何 Provider、Adapter、SDK 或 MCP Gateway
- RootCauseEngine 的输入必须可追溯到 Evidence

## 三级细化判断

结论：建议继续细化。

原因：该小目标仍包含多个动作或多个建议文件，继续拆分后更适合逐文件生成。

### 建议继续拆出的三级文档

- `01-提出多个假设.md`：提出多个假设
- `02-关联支持证据.md`：关联支持证据
- `03-给出置信度.md`：给出置信度
- `04-收敛结论.md`：收敛结论

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。
