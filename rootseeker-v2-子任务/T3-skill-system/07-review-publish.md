# Review Publish 迁移说明

## 结论

Skill 审核与发布不属于 `T3 Skill 系统改造` 的实现范围，已迁移到：

- `T6-skill-operations/02-review-flow.md`
- `T6-skill-operations/04-publisher.md`
- `06-自动沉淀与运营化.md`

## 原因

审核、发布、版本、灰度、回滚和评估都属于 Skill 运营闭环。它们依赖：

- `GeneratedSkillDraft`
- 审核人和审核意见
- 版本策略
- 回放评估结果
- 发布审计

这些不应放在 `T3`，否则会和 `T6` 重复。

## T3 中保留的相关能力

`T3` 只定义正式技能目录和加载规则：

- `builtin/`
- `team/`
- `generated/`
- `external/`

发布动作和审核状态统一由 `T6` 管理。

## 后续使用方式

如需实现审核和发布，请从 `T6-skill-operations/02-review-flow.md` 和 `T6-skill-operations/04-publisher.md` 开始，不要在 T3 下继续拆分本文件。
