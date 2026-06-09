# 定义 SkillExecutionPlan 与 GeneratedSki

## 上级目标

- 父级任务：`T1-core-contracts`
- 父级小目标：`03-skill-contracts.md`
- 父级标题：Skill 契约

## 三级目标

定义 SkillExecutionPlan 与 GeneratedSkillDraft

## 输入

SKILL.md frontmatter 与正文

## 输出

SkillSpec、SkillStepDefinition、GeneratedSkillDraft

## 建议落地文件

- `contracts/skill.py`

## 四级细化判断

结论：建议继续拆到四级。

原因：该三级目标仍包含可独立设计、实现或测试的子步骤，继续拆到四级更适合后续逐文件生成。

### 建议继续拆出的四级文档

- `01-data-fields.md`：字段与类型定义
- `02-validation-rules.md`：校验规则与默认值
- `03-serialization.md`：序列化与兼容性
- `04-contract-tests.md`：契约测试点

## 停止继续拆分的条件

- 只对应一个类、一个函数入口、一个 DTO 或一个 schema 片段。
- 实现时预计只改 1 个文件，且测试点不超过 3 个。
- 输入、输出和失败模式已经可以被一句话说明。

## 验收标准

- 能直接映射父级小目标的验收标准。
- 能明确目标文件、输入对象、输出对象和至少一个测试点。
