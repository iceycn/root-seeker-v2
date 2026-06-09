# SSRF 防护

## 上级目标

- 父级任务：`T13-config-infra`
- 父级小目标：`09-network-guard.md`
- 父级标题：Network Guard

## 三级目标

SSRF 防护

## 输入

url、request

## 输出

guarded request

## 建议落地文件

- `infra_core/network_guard.py`

## 四级细化判断

结论：建议继续拆到四级。

原因：该三级目标仍包含可独立设计、实现或测试的子步骤，继续拆到四级更适合后续逐文件生成。

### 建议继续拆出的四级文档

- `01-policy-inputs.md`：策略输入与信任边界
- `02-rules.md`：规则集合与匹配顺序
- `03-deny-reasons.md`：拒绝原因与错误结构
- `04-security-tests.md`：安全测试用例

## 停止继续拆分的条件

- 只对应一个类、一个函数入口、一个 DTO 或一个 schema 片段。
- 实现时预计只改 1 个文件，且测试点不超过 3 个。
- 输入、输出和失败模式已经可以被一句话说明。

## 验收标准

- 能直接映射父级小目标的验收标准。
- 能明确目标文件、输入对象、输出对象和至少一个测试点。
