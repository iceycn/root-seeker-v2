# T3 Skill 系统改造

## 1. 任务目标

本任务用于把 RootSeeker V2 从“流程硬编码系统”改造成“技能驱动系统”。

Skill 系统是 RootSeeker V2 的核心重构点之一，因为它决定了：

- 排查能力能否模块化
- 排查经验能否复用
- 大规模排查流程能否被拆成可管理的单元

边界说明：

- `T3` 只负责 Skill 的格式、注册、发现、过滤、组合和执行计划。
- `T3` 不负责从 Case 自动生成技能草稿。
- `T3` 不负责 Skill 审核、发布、版本、回滚和评估。
- 自动沉淀与运营化统一归属 `T6`。

---

## 2. 范围

本任务覆盖：

- `SKILL.md` 规范
- frontmatter 规范
- Skill 注册
- Skill 过滤
- Skill 组合

本任务不覆盖：

- 所有技能内容一次性补齐
- 所有业务域专项技能
- 最终技能运营平台 UI
- 自动生成 `GeneratedSkillDraft`
- Skill 审核、发布、版本、回滚和评估

---

## 3. 输入

- `T1` 的 `SkillSpec` 契约
- `T2` 的最小主链路
- `hermes-agent` 的 `SKILL.md` 结构经验

---

## 4. 输出

必须产出：

- Skill 目录结构
- Skill frontmatter 规范
- `SkillRegistry`
- `SkillComposer`
- `SkillExecutionPlan`
- builtin Skill 分类和加载规则

---

## 5. 一级拆解

### `T3.1` 定义 Skill 文件格式

先统一文档结构和 frontmatter 字段。

### `T3.2` 建立 Skill 注册与发现

让系统能够扫描和识别技能。

### `T3.3` 建立 Skill 选择与组合

让 Case 能自动匹配或组合技能。

### `T3.4` 建立 Builtin Skill 基础分类

定义内置技能分类、命名规则和加载边界，为 `T6` 的生成与发布提供目标目录。

---

## 6. 二级拆解

## 6.1 `T3.1` Skill 文件格式

### 建议字段

- `name`
- `slug`
- `description`
- `tags`
- `triggers`
- `required_tools`
- `conditions`
- `steps`
- `source_kind`
- `version`

### 文档正文建议结构

- `What this skill does`
- `When to use it`
- `Instructions`
- `Examples`
- `References`

### 文件任务

- `skills/templates/default_skill.md`
- `skills/schemas/skill-frontmatter.yaml`

## 6.2 `T3.2` Skill 注册与发现

### 模块任务

- 扫描 `builtin/`
- 扫描 `generated/`
- 扫描未来可能的 `external/`
- 建立技能目录缓存

### 类文件任务

- `skill_system/registry.py`
- `skill_system/frontmatter.py`
- `skill_system/cache.py`

## 6.3 `T3.3` Skill 选择与组合

### 模块任务

- 根据 `service_name` 匹配
- 根据 `symptom` 匹配
- 根据 `tags` 匹配
- 根据 `conditions` 做过滤
- 支持单 Skill 与复合 Skill

### 类文件任务

- `skill_system/composer.py`
- `skill_system/filtering.py`
- `skill_system/planning.py`

## 6.4 `T3.4` Builtin Skill 基础分类

### 模块任务

- 定义 `builtin/` 技能目录
- 定义 `team/` 技能目录预留
- 定义 `external/` 只读技能目录预留
- 定义默认技能 `base/default-log-triage`

### 类文件任务

- `skills/templates/default_skill.md`
- `skills/builtin/base/default-log-triage/SKILL.md`
- `skill_system/catalog_policy.py`

---

## 7. 推荐技能分类

建议先从以下技能类目开始：

- `base/log-triage`
- `trace/trace-link-analysis`
- `code/code-regression-check`
- `db/sql-timeout-triage`
- `middleware/mq-backlog-triage`
- `dependency/downstream-failure-check`

后续再扩展：

- `team-custom/*`
- `generated/*`

---

## 8. 风险

- 如果 Skill 规范太弱，后面技能内容会发散
- 如果 Skill 规范太强，后面新增技能会过于繁琐
- 如果没有分类和命名规则，后续技能数量增长后难以维护
- 如果把自动沉淀放在 T3，会和 T6 发生职责重叠

---

## 9. 验收标准

完成本任务时，应该满足：

- 系统可以扫描并识别多个 Skill
- 系统可以根据 Case 自动选择 Skill
- 系统可以组合至少两个 Skill
- 系统可以加载默认内置技能
- 自动生成、审核、发布能力不在 T3 验收范围内

---

## 10. 推荐实施顺序

1. 先定 `SKILL.md` 规范
2. 再建 `SkillRegistry`
3. 再建 `SkillComposer`
4. 再建 Skill 过滤与条件匹配
5. 最后建立 builtin Skill 分类和默认技能
