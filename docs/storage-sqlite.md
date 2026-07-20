# SQLite 数据源

SQLite 仍完整保留，适合单机开发、无 MySQL 环境，或从 Docker MySQL 一键回退。

## 快速启用

```bash
export ROOTSEEKER_STORAGE_BACKEND=sqlite
export ROOTSEEKER_SQLITE_DB_PATH=data/rootseeker.db   # 相对仓库根，或绝对路径
```

非 Docker 本地（`start-local.ps1`）**默认 sqlite**。切 MySQL：

```powershell
.\scripts\start-local.ps1 -Mysql
# 可选：-MysqlHost 127.0.0.1 -MysqlPort 3306
# 注意：Compose 内 MySQL 默认不 publish 端口，宿主机需自备可达的 MySQL，或临时改 compose 暴露端口。
```

Docker 回退 sqlite（且不起 mysql 容器）：

```bash
# .env
ROOTSEEKER_STORAGE_BACKEND=sqlite
COMPOSE_PROFILES=

./start.sh
```
## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `ROOTSEEKER_STORAGE_BACKEND` | `memory`（代码） | 设为 `sqlite` |
| `ROOTSEEKER_SQLITE_DB_PATH` | `data/rootseeker.db` | DB 文件路径；Docker 默认 `/app/data/rootseeker.db` |
| `ROOTSEEKER_ADMIN_STORE` | `auto` | `auto` 时跟 file（非 mysql 模式） |
| `ROOTSEEKER_CRON_STATE_STORE` | `auto` | 默认 `data/cron/scheduler-state.json` |
| `ROOTSEEKER_ERROR_HISTORY_STORE` | `auto` | 默认 file；可显式 `sqlite` |
| `ROOTSEEKER_ERROR_HISTORY_SQLITE_PATH` | `data/admin/error_history.db` | error history 独立库 |
| `ROOTSEEKER_ERROR_HISTORY_FILE` | `data/admin/error_history.json` | file 模式路径 |
| `ROOTSEEKER_CRON_STATE_PATH` | `data/cron/scheduler-state.json` | Cron 状态文件 |
| `ROOTSEEKER_ADMIN_CONFIG_PATH` | `data/admin/config.json` | Admin 配置文件 |

## 与 memory 的区别

| 后端 | 用途 |
|------|------|
| `memory` | 单测 / 冒烟，进程退出即丢 |
| `sqlite` | 本地持久化，单文件，多进程共用有写锁风险 |
| `mysql` | Docker 默认，适合 api/worker/scheduler 并发写 |

## 覆盖的数据

`ROOTSEEKER_STORAGE_BACKEND=sqlite` 时主业务写入同一 SQLite 文件：

- cases / evidence_packs / reports / tasks / checkpoints

Admin、Cron、error_history 在 `auto` 下仍用 **文件**（或 error_history 可单独设 `sqlite`），与 MySQL 模式不同。若也要文件以外的能力，可单独设：

```bash
ROOTSEEKER_ADMIN_STORE=file
ROOTSEEKER_CRON_STATE_STORE=file
ROOTSEEKER_ERROR_HISTORY_STORE=sqlite
```

## 运维

重置膨胀的 SQLite 库：

```bash
python scripts/reset_bloated_sqlite.py
```

## 与 MySQL 对照文档

见 [storage-mysql.md](./storage-mysql.md)。
