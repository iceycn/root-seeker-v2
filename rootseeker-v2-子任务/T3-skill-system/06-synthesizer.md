# Skill Synthesizer 迁移说明

## 结论

`SkillSynthesizer` 不属于 `T3 Skill 系统改造` 的实现范围，已迁移到：

- `T6-skill-operations/01-draft-builder.md`
- `T6-skill-operations/README.md`
- `06-自动沉淀与运营化.md`

## 原因

`T3` 只负责 Skill 的格式、注册、过滤、组合和内置技能目录。

从 Case 中自动生成技能草稿属于运营化闭环，依赖：

- 已完成 Case
- CaseReport
- 执行轨迹
- 回放评估
- 审核和发布门禁

这些都属于 `T6`。

## T3 中保留的相关能力

`T3` 只保留以下与生成有关的前置能力：

- 定义 `SKILL.md` 格式
- 定义 `SkillSpec`
- 定义 `SkillRegistry`
- 定义 `SkillComposer`
- 定义 builtin/team/generated 目录边界

## 后续使用方式

如需实现技能草稿生成，请从 `T6-skill-operations/01-draft-builder.md` 开始，不要在 T3 下继续拆分本文件。
