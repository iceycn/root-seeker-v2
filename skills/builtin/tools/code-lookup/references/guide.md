# 代码定位子技能

## 工具

- `code.search`
- `code.read`

## 搜索准则

- 使用当前最具体的线索搜索，避免无信号的宽泛搜索。
- 症状含 `file:line` 或 `code_path` 时可优先 file 查询或直接 read。

## 读取准则

- 优先 `code-search` 命中路径。
- 无目标则跳过 read。

## 前序步骤

- `normalize-incident`
- `code-search`（仅 read 步骤需要）
