# Command Groups

## 目标

实现命令组。

## 输入

args

## 输出

command result

## 建议文件

- `cli_commands/commands/*.py`

## 具体步骤

- case/skill/tool/plugin/channel/gateway/cron

## 验收标准

- 每个命令组可单独生成测试

## 三级细化判断

结论：可以暂时停止细化。

原因：该小目标当前已经接近单文件或单入口粒度，后续可在实现前再按类或函数拆分。

### 建议继续拆出的三级文档

- `01-case-skill-tool-plugin-channel-gatew.md`：case/skill/tool/plugin/channel/gateway/cron

### 停止继续拆分的条件

- 如果一个三级文档只对应一个类、一个函数入口或一个协议对象，就可以停止继续拆。
- 如果一个三级文档仍然会修改超过 3 个文件，应继续拆到四级。
- 如果一个三级文档同时包含数据契约、运行逻辑和持久化逻辑，应继续拆分。
- 三级文档的验收标准必须能直接映射到当前小目标的验收标准。

### 后续使用方式

- 后续让模型实现时，优先一次只选择上面一个三级文档。
- 每个三级文档再明确目标文件、输入对象、输出对象和测试点。
