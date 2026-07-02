---
name: Code lookup
description: "搜索并读取与故障相关的代码片段。"
---

# Code lookup

工具组：`code.search`、`code.read`。根据日志、trace 或症状中的线索定位代码。

详细准则见 `references/guide.md`。

## code.search

- 从 symptom 提取文件路径时用 `file:<path>` 查询；否则用症状首行关键词。
- 优先使用 `normalize-incident.extracted` 与日志/trace 线索。

## code.read

- 优先 `code-search` 步骤 hits[0] 的 path/repo。
- 其次 metadata.code_path、extracted.code_path、症状中的 `Foo.java:42`。
- 无明确目标时 `skip: true`。
