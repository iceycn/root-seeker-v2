---
name: Code lookup
description: "搜索并读取与故障相关的代码片段。"
---

# Code lookup

工具组：`code.search`、`code.read`、`code.find_callers`。根据日志、trace 或症状定位代码，并跨仓库追踪 caller。

详细准则见 `references/guide.md`。

## code.search

- 从 symptom 提取文件路径时用 `file:<path>` 查询；否则用症状首行关键词。
- 优先使用 `normalize-incident.extracted` 与日志/trace 线索。

## code.read

- 优先 `code-search` 步骤 hits[0] 的 path/repo。
- 其次 metadata.code_path、extracted.code_path、症状中的 `Foo.java:42`。
- 无明确目标时 `skip: true`。

## code.find_callers

- 输入 `normalize-incident.extracted.call_chain`。
- 默认 `prefer_graph=true`：先走 GitNexus 知识图谱，失败再回退 Zoekt 启发式。
- 跨已索引仓库搜索 caller，与运行时堆栈对齐；识别 `*Controller` HTTP 入口。
- 无 call_chain 时 `skip: true`。
- 若上一步 `graph.impact` 已给出充分 caller，仍应执行本步做对齐与入口识别。