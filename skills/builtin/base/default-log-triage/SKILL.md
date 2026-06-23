---
name: Default log triage
description: 内置默认值班日志链路排查流程，触发 RootSeeker 默认 flow plugin。
---

# Default log triage

用于 webhook 告警、历史告警 replay、以及人工发起的生产日志链路排查。目标是收集足够的真实证据，解释故障链路，定位最相关的代码区域，并产出可追溯的排查报告。

执行由内置 flow plugin `builtin.default_log_triage_flow` 完成。所有操作必须通过已注册的 MCP 工具调用，不允许绕过 gateway，也不允许伪造工具结果。

## 排查流程

每个阶段的详细执行准则放在 `references/` 下，主 Skill 只保留默认链路和加载导航：

- 输入归整：`references/01-normalize-incident.md`
- 服务目录：`references/02-resolve-service-catalog.md`
- 日志查询：`references/03-query-logs.md`
- Trace 链路：`references/04-fetch-trace-chain.md`
- 仓库与索引：`references/05-resolve-repository-context.md`
- 代码定位：`references/06-search-and-read-code.md`
- 报告通知：`references/07-report-and-notify.md`

1. 先规整告警输入。
   - 调用 `incident.normalize`，把原始告警载荷规整为后续排查统一使用的事件字段。
   - 提取服务名、租户、环境、trace id、症状文本、告警来源、时间窗口，以及显式的文件路径或代码符号。
   - 缺失字段只能作为未知信息记录，不能当作系统健康的证据。

2. 优先解析服务目录。
   - 在查日志或查代码前，先调用 `catalog.resolve_service`，把告警服务名映射到真实服务目录条目。
   - 服务解析后调用 `catalog.get_log_sources`，获取后续日志查询需要使用的具体日志源。
   - 如果服务目录无法解析，继续使用原始服务名排查，并把目录缺失记录为限制条件。

3. 在有 trace id 或错误时间窗口时查询日志。
   - 当告警载荷包含 trace id，或症状文本里能识别出 trace id 时，调用 `log.query_by_trace_id`。
   - 当 trace id 缺失、trace 日志为空、或症状像是重复错误模板时，调用 `log.query_by_template` 补充兜底证据。
   - 优先关注包含异常类、错误码、上下游服务、请求路径、模板 id、堆栈帧等线索的日志。

4. 在存在 trace 上下文后获取分布式链路。
   - 有 trace id 时调用 `trace.get_chain`。
   - 用 trace span 判断故障起点是在当前服务、上游调用方、下游依赖，还是重试/超时边界。
   - 如果 trace 数据不可用，把它记录为观测缺口，然后继续结合日志和代码证据排查。

5. 在选择代码片段前检查索引和仓库上下文。
   - 先调用 `index.get_status`，让报告明确代码索引是否可用、是否过期或缺失。
   - 当服务目录没有仓库映射、索引状态不清楚、代码搜索没有有效结果、或需要选择排查仓库时，调用 `repo.list`。
   - 仓库列表为空只能说明代码证据收集受阻，不能直接当作业务根因。

6. 只有在日志、trace 或告警文本提供线索后才搜索代码。
   - 当证据中出现异常类、方法名、文件路径、API 路由、错误码、队列/topic、SQL key、特性开关、日志模板等线索时，调用 `code.search`。
   - 搜索词应尽量使用当前最具体、最可靠的线索，避免没有信号时做宽泛搜索。

7. 只读取已选定目标的代码片段。
   - 当 `code.search` 返回文件命中、症状包含 `file:line` 线索、或元数据显式提供 `code_path` 时，调用 `code.read`。
   - 不要为了填充报告而随意读取文件。如果没有可读目标，应说明代码证据为什么无法收集。

8. 最后生成报告并通知。
   - 分别汇总服务目录、日志、trace、仓库、索引和代码证据。
   - 对未配置工具、缺失索引、空日志、不可用 trace 等情况标记限制条件。
   - 只有在报告已有证据和明确状态后，才调用 `notify.send`。

## 证据规则

- 每个结论都必须能追溯到工具证据。
- 缺失的工具数据应展示为限制条件或阻塞项。
- 当日志、trace 或代码互相矛盾时，不要基于单个弱信号下根因结论。
- 如果真实链路不完整，要给出下一步具体应该查询什么或补充哪个仓库动作。
