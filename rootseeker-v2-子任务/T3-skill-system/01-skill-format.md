# Skill 文件格式

## 目标

定义 SKILL.md frontmatter 和正文结构。

## 输入

Markdown

## 输出

frontmatter schema

## 建议文件

- `skills/schemas/skill-frontmatter.yaml`
- `skills/templates/default_skill.md`

## 具体步骤

- 定义必填字段
- 定义可选字段
- 定义 steps 结构
- 定义 source_kind

## 验收标准

- 每个 Skill 可被 schema 校验

## 三级细化判断

结论：建议继续细化。

原因：该小目标仍包含多个动作或多个建议文件，继续拆分后更适合逐文件生成。

### 建议继续拆出的三级文档

- `01-定义必填字段.md`：定义必填字段
- `02-定义可选字段.md`：定义可选字段
- `03-定义-steps-结构.md`：定义 steps 结构
- `04-定义-source_kind.md`：定义 source_kind
- `05-skills-schemas-skill-frontmatter.yam.md`：单独定义 ``skills/schemas/skill-frontmatter.yaml`` 的职责、输入输出和验收标准
- `06-skills-templates-default_skill.md.md`：单独定义 ``skills/templates/default_skill.md`` 的职责、输入输出和验收标准

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。
