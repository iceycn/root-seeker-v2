# MySQL 数据源

Docker 编排默认使用 MySQL。本地代码默认仍是 `memory`（便于单测），通过环境变量切换。

## 快速启用

```bash
# Docker（默认已是 mysql）
docker compose up -d --build

# 本地进程连接 Docker MySQL 或自建库
export ROOTSEEKER_STORAGE_BACKEND=mysql
export ROOTSEEKER_MYSQL_HOST=127.0.0.1
export ROOTSEEKER_MYSQL_PORT=3306
export ROOTSEEKER_MYSQL_USER=rootseeker
export ROOTSEEKER_MYSQL_PASSWORD=rootseeker
export ROOTSEEKER_MYSQL_DATABASE=rootseeker
```

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `ROOTSEEKER_STORAGE_BACKEND` | 代码 `memory` / Docker `mysql` | 设为 `mysql` 启用主业务库 |
| `ROOTSEEKER_MYSQL_HOST` | `127.0.0.1` | 主机；Compose 内为 `mysql` |
| `ROOTSEEKER_MYSQL_PORT` | `3306` | 端口 |
| `ROOTSEEKER_MYSQL_USER` | `rootseeker` | 用户 |
| `ROOTSEEKER_MYSQL_PASSWORD` | `rootseeker` | 密码 |
| `ROOTSEEKER_MYSQL_DATABASE` | `rootseeker` | 库名 |
| `ROOTSEEKER_ADMIN_STORE` | `auto` | `auto`/`file`/`mysql`；`auto` 在 mysql 模式下跟 MySQL |
| `ROOTSEEKER_CRON_STATE_STORE` | `auto` | `auto`/`file`/`mysql` |
| `ROOTSEEKER_ERROR_HISTORY_STORE` | `auto` | `auto`/`file`/`sqlite`/`mysql` |

主业务表：`cases` / `evidence_packs` / `reports` / `tasks` / `checkpoints`。  
Admin / Cron / error_history 在 `auto` + `storage_backend=mysql` 时一并走 MySQL。

## 初始化脚本（Docker 与自定义库共用）

脚本目录：仓库根目录 `mysql/init/`（不是 `docker/` 下）。

- Docker：挂载到 `/docker-entrypoint-initdb.d`，**仅在数据卷首次为空时**执行。
- 自定义数据库：

```bash
python scripts/init_mysql.py
# 或指定连接：
python scripts/init_mysql.py --host db.example.com --user app --password secret --database rootseeker
```

应用 Store 也会 `CREATE TABLE IF NOT EXISTS`，init 脚本用于显式建库与运维对齐。

清表（保留 schema）：

```bash
python scripts/reset_mysql.py --yes
```

### 旧 `.env` 覆盖默认

`start.sh` / `Makefile` 在已有 `.env` 时**不会**覆盖。若 `.env` 仍是：

```bash
ROOTSEEKER_STORAGE_BACKEND=sqlite
```

Compose 会跟着用 sqlite。全栈 Docker 请改为 `mysql`，或删除后从 `.env.docker` 重新复制。

凭据只需维护 `ROOTSEEKER_MYSQL_*`（Compose 的 `MYSQL_*` 已与之对齐）。

## Docker 数据卷（默认 named volume）

Compose 默认：

```yaml
volumes:
  - mysql-data:/var/lib/mysql
```

MySQL **不对外 publish 端口**，仅容器网络内可访问（服务名 `mysql:3306`）。

`mysql` 服务使用 profile `mysql`：

| `ROOTSEEKER_STORAGE_BACKEND` | 行为 |
|------------------------------|------|
| `mysql`（Docker 默认） | `COMPOSE_PROFILES=mysql`，启动 mysql 容器 |
| `sqlite` / `memory` | 清空 profile，**不启动** mysql 容器 |

`./start.sh` / `make docker-up` / `start.bat` 会按 `.env` 自动同步 profile。

### 改为宿主机目录 `./data/mysql`

编辑 `docker-compose.yml` 中 `mysql` 服务：

```yaml
volumes:
  - ./data/mysql:/var/lib/mysql
  - ./mysql/init:/docker-entrypoint-initdb.d:ro
```

注意：

1. 空目录才会跑 `mysql/init`；已有数据不会重跑。
2. Linux 上可能需 `chown -R 999:999 data/mysql`（官方镜像 mysql 用户 UID）。
3. `data/` 已在 `.gitignore` 中。

## 一键切回 SQLite（不起 MySQL）

```bash
# .env
ROOTSEEKER_STORAGE_BACKEND=sqlite
COMPOSE_PROFILES=

./start.sh
```

详见 [storage-sqlite.md](./storage-sqlite.md)。

## 驱动与连接池

使用 **PyMySQL** + 进程内连接池（`ROOTSEEKER_MYSQL_POOL_SIZE`，默认 8）。
