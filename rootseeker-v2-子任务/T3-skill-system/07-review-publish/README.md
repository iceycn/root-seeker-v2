# Review Publish 迁移说明

本目录中的旧拆分不再作为 `T3` 的执行入口。

实际归属：

- `T6-skill-operations/02-review-flow.md`
- `T6-skill-operations/04-publisher.md`
- `T6-skill-operations/02-review-flow/`
- `T6-skill-operations/04-publisher/`

原因：

- 审核、发布、版本、灰度、回滚和评估属于 Skill 运营闭环。
- `T3` 只负责正式技能目录、加载规则和组合能力。

后续不要继续在本目录下拆分或实现。
