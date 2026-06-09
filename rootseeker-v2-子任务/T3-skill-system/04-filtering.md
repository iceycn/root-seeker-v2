# Skill Filtering

## 目标

根据工具、条件和环境过滤技能。

## 输入

Case、tools、platform

## 输出

enabled skills

## 建议文件

- `skill_system/filtering.py`

## 具体步骤

- 按 required_tools 过滤
- 按 tags 过滤
- 按 conditions 过滤
- 按 disabled list 过滤

## 验收标准

- 不可用工具对应 Skill 不进入候选

## 三级细化判断

结论：建议继续细化。

原因：该小目标仍包含多个动作或多个建议文件，继续拆分后更适合逐文件生成。

### 建议继续拆出的三级文档

- `01-按-required_tools-过滤.md`：按 required_tools 过滤
- `02-按-tags-过滤.md`：按 tags 过滤
- `03-按-conditions-过滤.md`：按 conditions 过滤
- `04-按-disabled-list-过滤.md`：按 disabled list 过滤

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。
