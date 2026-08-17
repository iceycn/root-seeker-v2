# 文档模板（子任务必须遵循）

每个业务链路文档使用以下结构。禁止空泛描述；每一跳必须落到真实文件与函数。

```markdown
# <业务名>

## 1. 业务目标

用 3–6 句说明：谁触发、解决什么问题、成功时产出什么、失败时落到哪里。

## 2. 入口一览

| 入口类型 | 路径 / 符号 | 说明 |
| --- | --- | --- |
| HTTP / WS / CLI / 内部 | `apps/...` 或 `rootseeker/...:func` | 一句话 |

## 3. 主调用链（逐步）

按实际执行顺序编号。每一步必须包含：

- **步骤 N：短标题**
- 文件路径（仓库相对路径）
- 函数 / 方法名
- 输入关键字段
- 输出关键字段
- 下一步跳转到谁

推荐格式：

1. `apps/api/main.py` → `run_default_case`
   - 入：`RunCaseRequest(title, symptom, service_name, ...)`
   - 出：调用 `FlowRuntime.run_default`
2. `rootseeker/flow_runtime/runtime.py` → `FlowRuntime.run_default`
   - ...

需要时附 mermaid `sequenceDiagram` 或 `flowchart`（不超过 25 个节点）。

## 4. 关键数据结构

列出本链路读写的契约 / dataclass，标明定义文件：

- `CaseCreateRequest` — `rootseeker/contracts/case.py`
- 字段含义与谁填充、谁消费

## 5. 状态与副作用

- Case / Step / Task / Approval 状态如何变化
- 写入了哪些 Store（case / evidence / report / checkpoint / audit）
- 对外 I/O（MCP 工具、通知渠道、索引服务）

## 6. 分支与错误

| 条件 | 代码位置 | 行为 |
| --- | --- | --- |
| 审批拦截 | `...` | 返回 `APPROVAL_REQUIRED` |
| 缺配置 | `...` | fail-fast / 降级 |

## 7. 相关测试

列出能证明这条链路的测试文件（相对路径），各用一句话说明覆盖点。

## 8. 与其他文档的关系

交叉链接到 `docs/business-logic/` 下其他 md（用相对路径）。
```

约束：

- 用简体中文撰写。
- 不要编造不存在的函数名；读不到就写「未在代码中找到」。
- 不要大段粘贴源码；需要时只引用 5–15 行关键片段。
- 单文件控制在约 150–400 行 Markdown。
- 不要修改业务代码，只写文档。
- 不要 git commit。
