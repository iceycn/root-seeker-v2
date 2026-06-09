# Retry Recovery 三级目标索引

父级文件：`07-retry-recovery.md`

## 三级文件列表

- `01-指数退避.md`：指数退避（可以暂时停止在三级）
- `02-失败次数记录.md`：失败次数记录（可以暂时停止在三级）
- `03-清理-stale-running.md`：清理 stale running（可以暂时停止在三级）
- `04-cron-retry.py.md`：单独定义 ``cron/retry.py`` 的职责、输入输出和验收标准（建议继续拆到四级）
- `05-cron-recovery.py.md`：单独定义 ``cron/recovery.py`` 的职责、输入输出和验收标准（建议继续拆到四级）

## 使用方式

后续实现时，优先一次只选择一个三级文件；若该三级文件标记为“建议继续拆到四级”，先按其中的四级建议再拆一层。
