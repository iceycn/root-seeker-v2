---
name: Graph lookup
description: "查询 GitNexus 代码知识图谱。"
---

# Graph lookup

工具组：`graph.impact`、`graph.context`、`graph.query`、`graph.cypher`、`graph.trace`。

用于在词法（Zoekt）/语义（Qdrant）之外，基于结构图回答「谁调用了谁」「改动影响面」。

## graph.impact

- 输入故障方法符号，例如 `PopRecordService.insertPopRecordLogic`。
- 默认 `direction=upstream` 取 callers / blast radius。
- 优先使用 `normalize-incident.extracted.call_chain[0]` 解析出的类.方法。
- 无明确符号时 `skip: true`。

## graph.context

- 对同一符号做 360° 上下文（refs / process participation）。
- 与 `graph.impact` 共用符号；无符号时 `skip: true`。

## graph.query

- 概念/流程混合检索（BM25 + semantic + RRF）。
- 适合「认证流程」「订单落库」这类自然语言线索。

## graph.cypher / graph.trace

- 需要精确图查询或两点最短路径时使用；一般排查优先 impact/context。
