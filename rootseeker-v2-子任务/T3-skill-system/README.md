# T3 Skill System 小目标索引

## 文件列表

- `01-skill-format.md`：Skill 文件格式
- `02-frontmatter-parser.md`：Frontmatter 解析
- `03-registry.md`：Skill Registry
- `04-filtering.md`：Skill Filtering
- `05-composer.md`：Skill Composer
- `06-synthesizer.md`：迁移说明，实际归属 `T6-skill-operations`
- `07-review-publish.md`：迁移说明，实际归属 `T6-skill-operations`

## T3 边界

`T3` 只负责 Skill 的格式、注册、过滤、组合和内置技能目录。以下内容不在 `T3` 实现：

- 从 Case 自动生成技能草稿
- Skill 审核
- Skill 发布
- Skill 版本和回滚
- Skill 回放评估

这些能力统一由 `T6-skill-operations/` 承接。

## 推荐使用方式

后续实现时建议一次只打开一个小目标文件，并按其中的输入、输出、建议文件和验收标准生成代码。
