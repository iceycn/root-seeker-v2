# RootSeeker V2

面向生产环境日志链路的**企业级故障排查系统**。从告警接入、日志与链路采集、代码索引检索，到根因分析与报告通知，提供可编排、可审计、可回放的全链路自动化排查能力。

> **当前阶段**：MVP 主链路已在开发环境端到端跑通；核心平台模块已实现，部分能力仍在生产化加固中。详见 [实现状态](docs/implementation-status.md)。

## 目录

- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [常用命令](#常用命令)
- [默认排查链路](#默认排查链路)
- [API 服务](#api-服务)
- [管理控制台](#管理控制台)
- [代码检索（Zoekt + Qdrant）](#代码检索zoekt--qdrant)
- [Docker 部署](#docker-部署)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [模块状态](#模块状态)

## 核心能力

| 能力 | 说明 |
| --- | --- |
| **Skill 驱动流程** | 内置 `default-log-triage` 流程，按步骤加载工具 Skill，经 MCP Gateway 调用外部能力 |
| **MCP 工具平面** | 统一内部/外部工具调用，内置策略守卫与审计 |
| **证据与根因** | 证据归集、多假设推理、规则引擎 + 可选 LLM 报告增强 |
| **代码索引** | Git 仓库同步、Zoekt 词法检索、Qdrant 语义搜索、LSP 符号查询 |
| **多渠道接入** | Webhook / 阿里云 SLS / Prometheus 等告警归一化；飞书 / 钉钉 / 企微 / Slack 等通知 |
| **控制平面** | Gateway WebSocket、Case/Flow/Skill/Tool 方法、审批与回放质量门禁 |
| **持久化与回放** | SQLite 可选持久化；Case 回放与评估质量门禁 |

**环境要求**：Docker + Docker Compose（推荐快速体验）· Python 3.11+（本地开发与贡献代码）

## 快速开始

推荐使用 **Docker Compose** 一键启动完整栈（API、Admin、Worker、Scheduler、Zoekt、Qdrant），无需本机安装 Python 依赖。

### 1. 准备配置

```bash
cp .env.docker .env   # 按需修改 LLM、SLS 等（不配置也可启动基础服务）
```

### 2. 启动服务

```bash
make docker-up
# 或
docker compose up -d --build
```

### 3. 验证

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/healthz | API 健康检查 |
| http://localhost:8000/docs | Swagger API 文档 |
| http://localhost:8010/admin | 管理控制台 |

```bash
curl http://localhost:8000/healthz
docker compose logs -f api    # 查看日志
make docker-down              # 停止服务
```

默认使用 SQLite 持久化 + hash embedding，**无需外部 AI 服务**即可运行。如需 LLM 报告增强，在 `.env` 中配置 `ROOTSEEKER_LLM_*`。

### 本地开发（可选）

贡献代码或跑单元测试时使用：

```bash
pip install -e ".[dev]"   # 或 make install
pytest                    # 或 make test
make demo                 # 本地端到端演示（无需启动服务）
make api && make demo-api # API 联调
```

## 常用命令

### 本地开发

| 命令 | 说明 |
| --- | --- |
| `make install` | 安装项目及开发依赖 |
| `make test` | 运行全部测试 |
| `make demo` | 本地端到端演示 |
| `make api` | 启动 API（`:8000`） |
| `make admin` | 启动管理控制台（`:8010`） |
| `make demo-api` | API 联调脚本 |
| `make worker` | 单次 Worker 任务（含 demo seed） |
| `make worker-loop` | Worker 轮询模式 |
| `make scheduler` | 单次 Cron 调度 |
| `make scheduler-loop` | Cron 轮询模式 |

### CLI 入口

```bash
rootseeker demo          # 本地演示
rootseeker replay        # Case 回放
rootseeker-admin         # 管理控制台
rootseeker-worker        # 后台任务 Worker
rootseeker-scheduler     # 定时调度器
```

**Worker 常用参数**：`--loop --interval-seconds --max-empty-polls --max-runs --seed-demo`

**Scheduler 常用参数**：`--loop --schedule --timezone --state-path --run-immediately/--no-run-immediately --interval-seconds --max-runs --retries --retry-delay-seconds`

### Docker

| 命令 | 说明 |
| --- | --- |
| `make docker-up` | 构建并启动全部服务 |
| `make docker-down` | 停止服务 |
| `make docker-logs` | 查看 API 日志 |
| `make docker-ps` | 查看容器状态 |

## 默认排查链路

内置 Flow `default-log-triage` 按步骤执行：告警归一化 → 服务目录解析 → 日志查询 → 链路追踪 → 仓库索引 → 代码检索 → 报告通知。

```mermaid
flowchart LR
  A[告警/Case] --> B[Skill Flow]
  B --> C[Step]
  C --> D[Plugin Capability]
  D --> E[MCP ToolCall]
  E --> F[Tool Result]
  F --> G[Evidence]
  G --> H[RootCauseEngine]
  H --> I[CaseReport]
  I --> J[Notify]
```

运行时调用链：

```
Case → Skill → Step → Plugin → MCP ToolCall → Evidence → RootCauseEngine → CaseReport → notify
```

## API 服务

```bash
uvicorn apps.api.main:app --reload --port 8000
# 或
make api
```

### 主要端点

| 端点 | 说明 |
| --- | --- |
| `GET /healthz` · `GET /readyz` | 健康检查与就绪探针 |
| `GET /metrics` | Prometheus 指标 |
| `GET /skills` | 可用 Skill 列表 |
| `POST /cases/run-default` | 执行默认排查流程 |
| `GET /cases/{case_id}` | Case 详情 |
| `GET /reports/{case_id}` | 分析报告 |
| `GET /evidence/{case_id}` | 证据包 |
| `GET /cases/{case_id}/audit` | 审计记录 |
| `GET /flows/checkpoints` | Flow 检查点列表 |
| `POST /webhook/{channel}` | 外部告警接入（webhook / aliyun / sls / prometheus） |
| `WebSocket /gateway/ws` | 控制平面通信 |
| `GET /gateway/connections` | 活跃 WebSocket 连接 |

### API 文档

- Swagger UI：http://localhost:8000/docs
- ReDoc：http://localhost:8000/redoc
- OpenAPI JSON：http://localhost:8000/openapi.json

## 管理控制台

独立于 API 的运维管理界面，用于 Skill/插件/MCP 工具、仓库同步、服务目录、代码语义搜索等日常操作。

```bash
make admin
# 或
ADMIN_PORT=8010 rootseeker-admin
# 或
uvicorn apps.admin.main:app --host 127.0.0.1 --port 8010
```

访问：http://127.0.0.1:8010/admin

**当前能力：**

- 查看 Skills、Plugins 及已注册 MCP 工具
- 注册 / 注销 / 同步 / 检查 Git 仓库
- 触发 Zoekt / Qdrant 索引（与 API 共用同一套 repo tools）
- 查看与更新内存服务目录
- Qdrant 语义代码搜索
- 运行时健康与索引状态

## 代码检索（Zoekt + Qdrant）

代码索引支持 **本机二进制**（推荐本地开发）和 **Docker Compose** 两种方式。

### 本机开发（无 Docker）

使用仓库内 `config/qdrant_config.yaml`，数据目录为 `./data/`。

**1. 安装 Zoekt（需 Go）**

```bash
go install github.com/sourcegraph/zoekt/cmd/zoekt-webserver@latest
go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest
export PATH="$(go env GOPATH)/bin:$PATH"
```

**2. 安装 Qdrant 二进制**

从 [Qdrant Releases](https://github.com/qdrant/qdrant/releases) 下载对应平台，将可执行文件命名为 `qdrant` 并加入 `PATH`，或放到 `tools/qdrant/qdrant`，或通过 `ROOTSEEKER_QDRANT_BINARY` 指定绝对路径。

**3. 启动与联调**

```bash
./scripts/install_local_codesearch_deps.sh   # 检查/安装 Zoekt，提示 Qdrant
./scripts/start_zoekt_qdrant.sh              # 后台启动，日志见 data/run/*.log
./scripts/run_real_codesearch_smoke.sh       # 示例仓 + 索引 + 语义搜索联调
./scripts/stop_zoekt_qdrant.sh               # 停止本机进程
```

**4. Embedding 配置**

默认 `ROOTSEEKER_EMBEDDING_PROVIDER=hash`，使用本地确定性向量，适合无外部服务的 Qdrant 写入/查询联调。接入真实 embedding 服务：

```bash
export ROOTSEEKER_EMBEDDING_PROVIDER=openai_compatible
export ROOTSEEKER_EMBEDDING_BASE_URL=https://api.openai.com/v1
export ROOTSEEKER_EMBEDDING_API_KEY=...
export ROOTSEEKER_EMBEDDING_MODEL=text-embedding-3-small
export ROOTSEEKER_EMBEDDING_DIMENSION=1536
```

### Docker 方式

```bash
docker compose --profile codesearch up -d --build zoekt qdrant
# 或使用脚本
./scripts/start_zoekt_qdrant_docker.sh
```

## Docker 部署

快速启动见上文 [快速开始](#快速开始)。以下为服务说明与可选组件。

### 服务一览

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| api | 8000 | REST API |
| admin | 8010 | 管理控制台 |
| worker | — | 后台任务处理 |
| scheduler | — | Cron 定时调度 |
| zoekt | 6070 | 词法代码检索 |
| qdrant | 6333 (gRPC 6334) | 向量语义检索 |
| jaeger | 16686 | 链路追踪可视化（可选） |

### 可选 Profile

```bash
# 链路追踪
docker compose --profile tracing up -d

# 代码检索
docker compose --profile codesearch up -d --build zoekt qdrant

# 全部可选服务
docker compose --profile tracing --profile codesearch up -d
```

## 配置说明

- **Docker 部署**：以 [`.env.docker`](.env.docker) 为模板（`cp .env.docker .env`）
- **本地开发 / 全量参考**：见 [`.env.example`](.env.example)

以下为常用配置分组。

### 内部适配器

```bash
# composite（默认）：SLS / Jaeger / Zoekt + RepoSync
export ROOTSEEKER_INTERNAL_ADAPTER_KIND=composite
export ROOTSEEKER_NOTIFY_DEFAULT_URL=https://example.com/my-webhook

# http：将内部工具委托给外部 HTTP 服务
export ROOTSEEKER_INTERNAL_ADAPTER_KIND=http
export ROOTSEEKER_INTERNAL_HTTP_BASE_URL=http://127.0.0.1:9000
```

### 持久化存储

默认内存存储，适合本地冒烟测试。启用 SQLite：

```bash
export ROOTSEEKER_STORAGE_BACKEND=sqlite
export ROOTSEEKER_SQLITE_DB_PATH=data/rootseeker.db
```

### Cron 调度状态

```bash
export ROOTSEEKER_CRON_STATE_PATH=data/cron/scheduler-state.json
rootseeker-scheduler --loop --schedule "*/5 * * * *"
```

### LLM 报告增强

配置 OpenAI 兼容接口后，默认排查流程会用模型增强 `CaseReport.summary` 与 `root_cause`，规则引擎结果保留在 report metadata 中：

```bash
export ROOTSEEKER_LLM_BASE_URL=https://api.openai.com/v1
export ROOTSEEKER_LLM_API_KEY=...
export ROOTSEEKER_LLM_MODEL=gpt-4o-mini
# 可选
export ROOTSEEKER_LLM_PROVIDER_NAME=openai
export ROOTSEEKER_LLM_ENABLED=false   # 关闭 LLM 增强
```

### 审批工作流通知

```bash
export ROOTSEEKER_APPROVAL_WEBHOOK_URL=https://example.com/approval-workflow
export ROOTSEEKER_APPROVAL_WEBHOOK_TIMEOUT_SECONDS=5
```

### 代码检索关键变量

| 变量 | 说明 |
| --- | --- |
| `ZOEKT_ENDPOINT` / `ROOTSEEKER_ZOEKT_ENDPOINT` | Zoekt HTTP API |
| `QDRANT_ENDPOINT` / `ROOTSEEKER_QDRANT_ENDPOINT` | Qdrant REST |
| `QDRANT_COLLECTION_NAME` | 向量集合名（默认 `code_chunks`） |
| `ROOTSEEKER_ZOEKT_INDEX_DIR` | zoekt-index 输出目录 |
| `ROOTSEEKER_EMBEDDING_PROVIDER` | `hash`（默认）或 `openai_compatible` |
| `SLS_*` | 阿里云 SLS 日志服务 |
| `JAEGER_ENDPOINT` | Jaeger 链路追踪 |

## 项目结构

```
rootseeker/     # 核心运行时与业务模块
apps/           # 应用入口（api / admin / worker / scheduler / cli）
skills/         # 内置与自定义 Skill
plugins/        # 内置与自定义 Plugin
mcp_servers/    # 内部与外部 MCP 工具实现
tests/          # 单元、集成与回放测试
scripts/        # 可运行辅助脚本
docs/           # 架构与实现状态文档
k8s/            # Kubernetes 部署清单
```

## 模块状态

状态说明：`Completed` 已实现并有测试覆盖 · `Partial` 已实现但待加固 · `Planned` 尚未达到目标设计深度

| 模块 | 状态 |
| --- | --- |
| 骨架、契约、存储/审计 | Completed |
| Plugin / Skill / MCP 平面 | Completed |
| 服务目录、日志平面、代码索引 | Completed |
| 证据、根因引擎、Task/Flow 运行时 | Completed |
| 默认 Flow + API/Worker/Scheduler 入口 | Completed |
| 回放/评估 + CLI/Cron 回放 | Completed |
| 渠道路由（多渠道归一化与通知） | Completed |
| Gateway 控制平面（WebSocket + 鉴权/限流） | Completed |
| 基础设施（安全文件、网络守卫、脱敏） | Completed |
| LLM 报告增强、检查点恢复、Skill 自动合成 | Completed |
| SQLite 持久化、多渠道适配器 | Completed |
| Agent Runtime（LLM 工具规划、自修复） | Partial |
| 审批策略、部署策略编排 | Partial |

详细范围与缺口见 [docs/implementation-status.md](docs/implementation-status.md)。

## 相关文档

- [实现状态与缺口](docs/implementation-status.md)
- [Case 状态机](docs/architecture/case-state-machine.md)
- [状态机总览](docs/architecture/state-machines.md)
