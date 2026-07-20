# 交互式安装向导 — 设计说明

日期：2026-07-20  
状态：已确认  
相关文档：`docs/storage-mysql.md`、`docs/storage-sqlite.md`、`start.sh`、`scripts/start-local.ps1`

## 目标

为 RootSeeker V2 提供**渐进式、交互式**的首次安装向导，做到：

1. **自动探测 Docker**：若已安装且 daemon 可用，优先走 Docker Compose 全栈。
2. **无 Docker 时走本机完整安装**（不是只装 API）。
3. **支持 Windows / macOS / Linux**（共用一份 Python 向导 + 薄包装脚本）。
4. **本机路径下询问存储**：便携 MySQL / 已有 MySQL / 内置 SQLite。
5. **本机尽量装齐索引依赖**（Zoekt / Qdrant / GitNexus）；失败可跳过，不阻断 API/Admin。

v1 不做：

- Kubernetes 引导安装（继续用现有 `start.sh k8s`）
- 替换日常启停用的 `start.sh` / `start.bat`
- 保证无 Node/Docker 时 GitNexus 一定可用

## 已锁定决策

| 议题 | 选择 |
|------|------|
| 路径选择 | 自动探测 Docker → 优先 Docker；否则本机 |
| 操作系统 | Windows、macOS、Linux |
| 本机完整度 | 尽量装索引器（不是最小 API-only） |
| 「安装 MySQL」 | 便携版放到项目 `.tools/`（不用 brew/apt/winget） |
| 实现形态 | Python 主向导 + `setup.ps1` / `setup.sh` 薄包装 |
| 架构 | 分步模块 + `.setup-state.json` 续跑（方案 2） |

## 整体流程（中文）

```text
setup.ps1 / setup.sh          ← 用户双击或命令行启动（按系统选）
        │
        ▼
scripts/setup_wizard.py       ← 真正的交互向导（Python）
        │
        ├─【步骤 1】欢迎 + 环境探测
        │     探测：Python 版本、操作系统、Docker 是否可用、
        │     端口占用、是否已有 .env / 安装进度文件
        │
        ├─【步骤 2】选择安装路径（可改默认）
        │     · Docker 可用 → 默认「路径 A：Docker 全栈」
        │     · Docker 不可用 → 默认「路径 B：本机完整安装」
        │
        ├─【路径 A：Docker 全栈】
        │     ① 合并写入 .env（默认 mysql + 启用 mysql 编排 profile）
        │     ② 可选填写 LLM 密钥（直接回车可跳过）
        │     ③ 询问：只编译镜像 / 编译并启动（默认：编译并启动）
        │     ④ 准备 Zoekt 二进制 + 执行 docker compose
        │     ⑤ 健康检查（API / Admin）
        │     ⑥ 打印访问地址与后续命令
        │
        └─【路径 B：本机完整安装】
              ① 创建虚拟环境 .venv，pip 安装项目依赖
              ② 选择数据存储（三选一，见下文）
              ③ 尽量安装并启动索引组件（Zoekt / Qdrant / GitNexus）
              ④ 后台启动 API(:8000) 与 Admin(:8010)
              ⑤ 健康检查
              ⑥ 打印结果汇总（哪些成功、哪些跳过）
```

**续跑**：再次执行向导时读取 `.setup-state.json`，跳过已完成步骤，从中断处继续。

## 文件布局

```text
setup.sh                          # macOS/Linux 入口：找到 python3 后调用向导
setup.ps1                         # Windows 入口：找到 python 后调用向导
scripts/setup_wizard.py           # 交互编排（只负责问答与调度，不堆业务细节）
scripts/setup/
  __init__.py
  ui.py                           # 彩色输出、确认、单选、进度提示
  state.py                        # 读写 .setup-state.json（安装进度）
  detect.py                       # 探测 OS / Python / Docker / 端口
  env_writer.py                   # 安全合并写入 .env（不悄悄清掉已有密钥）
  docker_path.py                  # Docker：compose 编译/启动 + 健康检查
  native_path.py                  # 本机：venv、pip、启动 uvicorn
  portable_mysql.py               # 便携 MySQL：下载 / 初始化 / 启停
  existing_mysql.py               # 已有 MySQL：连通探测 + 跑 init_mysql.py
  indexers.py                     # 本机准备 Zoekt / Qdrant / GitNexus
  health.py                       # 轮询 HTTP /healthz
.tools/                           # 便携依赖存放目录（加入 .gitignore）
.setup-state.json                 # 安装进度（加入 .gitignore）
```

职责边界：

- **向导**只编排步骤；下载地址、进程启停放在各模块里。
- **只有 `env_writer` 写 `.env`**（原子写入；默认不覆盖已有密钥）。
- Docker 路径尽量复用现有：`scripts/sync-compose-storage.sh`、`docker/prepare-zoekt.*`、`docker compose`。

`.gitignore` 需增加：`.tools/`、`.setup-state.json`。

## 路径 A — Docker 全栈（逐步说明）

1. 若没有 `.env`，从 `.env.docker` **合并生成**（不要整文件盲覆盖）。
2. 默认：`ROOTSEEKER_STORAGE_BACKEND=mysql`，`COMPOSE_PROFILES=mysql`。
3. 可选询问 LLM 相关变量（回车跳过）。
4. 询问：仅 build，还是 build + up（默认后者）。
5. 需要时准备 Zoekt 二进制；执行 `docker compose up -d --build`（或只 build）。
6. 轮询 `http://127.0.0.1:8000/healthz` 与 Admin 健康检查。
7. 打印访问地址，以及常用命令（看日志、停止服务等）。

若用户改选 SQLite：仍可用现有 profile 同步逻辑，**不启动 mysql 容器**。

## 路径 B — 本机完整安装

### Python 运行时

- 没有 `.venv` 就创建。
- 先升级 pip，再 `pip install -e ".[dev]"`。
- Python 低于 3.11 直接失败并提示。

### 存储三选一（交互询问）

| 选项 | 行为（中文说明） |
|------|------------------|
| ① 便携 MySQL | 按系统下载官方压缩包到 `.tools/mysql/<版本>/`；数据目录 `.tools/mysql-data/`；初始化后后台启动；默认端口 **3307**（避免和系统 3306 冲突）；写入 `.env`；执行 `scripts/init_mysql.py` 建表 |
| ② 已有 MySQL | 询问主机/端口/用户/密码/库名 → 探测能否连通 → 写 `.env` → 执行建表脚本 |
| ③ SQLite | 写入 `ROOTSEEKER_STORAGE_BACKEND=sqlite` 与库文件路径 `data/rootseeker.db` |

便携 MySQL 补充约定：

- 版本号钉死在 `portable_mysql.py` 常量里（实现时选定具体 LTS 小版本）。
- 有校验和则校验；没有则警告后继续。
- PID 写入 `.tools/mysql.pid`，向导可提供停止命令。

### 索引组件（尽量安装，失败可跳过）

| 组件 | 策略（中文） |
|------|--------------|
| Zoekt | 复用/扩展现有 `docker/prepare-zoekt.*`；二进制放到 `docker/bin/` 或 `.tools/zoekt/`；本机启动搜索与索引服务（6070/6071） |
| Qdrant | 下载对应平台官方包到 `.tools/qdrant/` 并启动；失败则标记跳过 |
| GitNexus | 探测 Node/`npx` 或已有服务；能起则起，否则跳过并提示以后用 Docker 补 |

原则：索引任一步失败 → 记入进度 → **不阻断** API/Admin；结束时汇总「已启用 / 已跳过」。

### 应用进程

- 后台启动 API（8000）与 Admin（8010）。
- PID 记入进度文件，方便下次检测是否已在运行。

## 错误处理

- 每一步结果：成功 / 可重试失败 / 可跳过失败。
- 下载失败：提示可设代理（`HTTP_PROXY` 等），允许重试；便携 MySQL 可降级改选 SQLite。
- 端口被占用：建议换端口或自行结束占用进程（**不强制杀进程**）。
- 写 `.env`：原子写入；已有密钥默认保留，除非用户确认覆盖。
- 按 Ctrl+C：保存进度，并提示下次如何续跑。

## 非交互参数（给脚本 / CI 用）

```text
# 无人值守：Docker + MySQL
python scripts/setup_wizard.py --yes --path docker --storage mysql

# 无人值守：本机 + SQLite
python scripts/setup_wizard.py --yes --path native --storage sqlite

# 从断点继续
python scripts/setup_wizard.py --resume

# 查看当前安装状态
python scripts/setup_wizard.py --status
```

使用 `--yes` 时若缺少必填参数：直接非零退出（不会偷偷改回交互模式）。

## 与现有入口的关系

| 入口 | 用途 |
|------|------|
| `setup.ps1` / `setup.sh` | **初次安装 / 续装向导**（新做） |
| `start.sh` / `start.bat` | 配置完成后的 Docker 日常启停（保留） |
| `scripts/start-local.ps1` | Hybrid 快捷启动；向导结束时可提示 |

## 测试计划

- 单测（网络/进程打桩）：环境探测、`.env` 合并、进度续跑、便携 MySQL 平台 URL 选择、命令行参数解析。
- 手工验收：Win / macOS / Linux × Docker 路径；至少一条本机 SQLite；网络允许时一条便携 MySQL。

## 验收标准

1. 三端在有 Docker 时，能走 Docker 路径完成编译启动，API 健康检查通过。
2. 无 Docker 时，本机路径能建 venv、装依赖，并用 SQLite 拉起 API/Admin。
3. 便携 MySQL：下载 → 启动 → 建表 → 应用配置指向它（连通探测通过）。
4. 索引部分失败时，API/Admin 仍能启动，结束有跳过清单。
5. 中断后续跑，不重复下载已完成的大文件。
6. 有单测覆盖探测 / 环境合并 / 续跑（下载类可 mock）。

## 实现时再定的细节（不阻塞设计）

- 具体 MySQL 小版本与下载镜像地址：实现时钉死，优先官方源 + checksum。
- Qdrant / GitNexus 在各系统上的启动命令差异：收进 `indexers.py`，失败原因写清楚。
- Windows 用合适的后台进程方式；Unix 用 PID 文件 + 后台进程。
