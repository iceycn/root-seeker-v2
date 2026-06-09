# T11 CLI 命令体系

## 1. 任务目标

本任务用于借鉴 OpenClaw CLI 和命令模块，为 RootSeeker V2 建立工程化命令行体系。

CLI 不是附属工具，而是企业级系统中用于：

- 调试
- 回放
- 诊断
- 配置校验
- 插件管理
- Skill 管理
- 通道测试

的重要入口。

参考文档：

- `/Users/beisen/PycharmProjects/openclaw-analysis/02-CLI和命令模块分析.md`
- `/Users/beisen/PycharmProjects/openclaw-analysis/10-核心模块方法级分析.md`

---

## 2. 范围

本任务覆盖：

- CLI Command Registry
- Command Catalog
- Pre-action Hooks
- Config Guard
- Doctor / Status
- Case / Skill / Tool / Plugin / Channel 命令

本任务不覆盖：

- 完整 TUI
- 图形化交互界面

---

## 3. 输入

- 命令行参数
- 配置文件
- Gateway 地址
- 本地工作区路径

---

## 4. 输出

- 命令执行结果
- JSON 输出
- 诊断报告
- 回放结果

---

## 5. 一级拆解

### `T11.1` 命令注册

建立命令目录和懒加载机制。

### `T11.2` Pre-action Hooks

统一处理配置、日志、环境检查。

### `T11.3` 核心命令组

实现 Case、Skill、Tool、Plugin、Channel 等命令。

### `T11.4` Doctor / Status

提供诊断和状态检查。

---

## 6. 二级拆解

## 6.1 `T11.1` 命令注册

### 类文件任务

- `cli_commands/registry.py`
- `cli_commands/catalog.py`
- `cli_commands/context.py`

## 6.2 `T11.2` Pre-action Hooks

### 职责

- 加载配置
- 设置日志级别
- 检查 Gateway
- 检查工作区
- 检查插件

### 类文件任务

- `cli_commands/pre_action.py`
- `cli_commands/config_guard.py`

## 6.3 `T11.3` 核心命令组

### 命令建议

- `rootseeker case create`
- `rootseeker case replay`
- `rootseeker case status`
- `rootseeker skill list`
- `rootseeker skill review`
- `rootseeker tool list`
- `rootseeker plugin list`
- `rootseeker channel test`
- `rootseeker gateway status`

### 类文件任务

- `cli_commands/commands/case.py`
- `cli_commands/commands/skill.py`
- `cli_commands/commands/tool.py`
- `cli_commands/commands/plugin.py`
- `cli_commands/commands/channel.py`

## 6.4 `T11.4` Doctor / Status

### 检查项

- 配置有效性
- SecretRef 可解析性
- Gateway 可达性
- MCP 工具可用性
- 插件 manifest 有效性
- 日志目录权限

### 类文件任务

- `cli_commands/commands/doctor.py`
- `cli_commands/commands/status.py`

---

## 7. 风险

- 如果 CLI 后置，调试和回放会依赖临时代码
- 如果没有 JSON 输出，自动化脚本很难集成
- 如果没有 pre-action hooks，每个命令会重复做配置检查

---

## 8. 验收标准

- CLI 能列出命令目录
- CLI 能执行 Case 回放
- CLI 能检查配置和插件
- CLI 能输出机器可读 JSON

---

## 9. 推荐实施顺序

1. 建 Command Catalog
2. 建 Pre-action Hooks
3. 建 Case / Skill / Tool 命令
4. 建 Plugin / Channel 命令
5. 建 Doctor / Status
