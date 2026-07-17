# RootSeeker V2

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/docker-ready-blue.svg" alt="Docker">
</p>

**RootSeeker V2** 是面向公司内网的 **AI 驱动故障排查与根因发现平台**。从一条告警或报错日志出发，自动还原故障现场、检索私有代码与知识图谱、汇聚证据并产出可落地的根因报告——帮你告别「通灵」式 Debug。

**核心价值**：把研发从繁杂的证据收集中解放出来，缩短排查时长，减少现网应急损失。支持告警接入 → 日志/链路采集 → 代码检索与图谱 → 根因分析与多渠道通知的全链路自动化；Skill 可编排、MCP 可审计、Case 可回放。支持私有化部署，代码与日志可不出内网。

**使用它能带来什么**：不再对着堆栈瞎猜；自动关联 Trace / 日志上下文；Zoekt + Qdrant + GitNexus 构建私有代码索引；报告可推送飞书 / 钉钉 / 企微 / Slack；运维控制台支持仓库同步、定时任务与错误排查助手。

> **当前阶段**：MVP 主链路已在开发环境端到端跑通。详见 [实现状态](docs/implementation-status.md)。

> 📮 项目快速迭代中：需求与建议欢迎通过 [Issue](https://github.com/iceycn/root-seeker-v2/issues) 提交。

---

## 目录

- [为什么选择 RootSeeker？](#为什么选择-rootseeker)
- [核心特性](#核心特性)
- [工作原理](#工作原理)
- [快速开始](#快速开始)
- [Hybrid 本地开发](#hybrid-本地开发)
- [常用命令](#常用命令)
- [API 与管理控制台](#api-与管理控制台)
- [代码索引](#代码索引)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [模块状态](#模块状态)
- [相关文档](#相关文档)
- [贡献指南](#贡献指南)
- [License](#license)

---

## 为什么选择 RootSeeker？

传统故障排查依赖人工经验，SRE 需要在日志平台、监控系统和 IDE 之间反复横跳。RootSeeker 旨在解决这些痛点：

- **告别「通灵」式 Debug**：不再对着报错堆栈瞎猜，结合代码检索定位到具体文件与行号。
- **全息现场还原**：自动拉取关联日志与 Trace 上下文（API 入参、SQL、RPC 等）。
- **懂你的私有代码**：Zoekt 词法检索 + Qdrant 语义搜索 + GitNexus 知识图谱，覆盖精确匹配与业务意图。
- **可编排、可审计**：内置 Skill Flow 经 MCP Gateway 调用工具，策略守卫与审计贯穿全程。
- **可运维**：Admin 控制台管理仓库同步、定时任务、错误排查助手与索引状态。

---

## 核心特性

- **Skill 驱动流程**：内置 `default-log-triage`，按步骤经 MCP Gateway 调用工具，可编排、可断点恢复。
- **MCP 工具平面**：统一内外部工具调用，含策略守卫、审批与审计。
- **证据与根因**：证据归集、多假设推理；规则引擎 + 可选 LLM 增强报告。
- **三引擎代码索引**：Zoekt（词法）+ Qdrant（语义）+ GitNexus（图谱），均支持容器内远程索引。
- **运维控制台**：仓库注册/同步、定时任务（如每小时同步变更仓）、错误排查助手、服务目录。
- **多渠道接入与触达**：Webhook / 阿里云 SLS / Prometheus 入站；飞书 / 钉钉 / 企微 / Slack 出站。
- **持久化与回放**：SQLite 可选持久化；Case 回放与质量门禁。
- **数据安全**：支持私有化部署与本地/内网 LLM，代码与日志可不出公网。

**环境要求**：Docker + Compose（推荐）· Python 3.11+（本地开发）

---

## 工作原理

默认排查链路（`default-log-triage`）：告警归一化 → 服务目录 → 日志查询 → 链路追踪 → 仓库/索引 → 代码检索 / 图谱 → 报告通知。

```mermaid
flowchart LR
  A[告警/Case] --> B[Skill Flow]
  B --> C[Step]
  C --> D[Plugin Capability]
  D --> E[MCP ToolCall]
  E --> F[Evidence]
  F --> G[RootCauseEngine]
  G --> H[CaseReport]
  H --> I[Notify]
```

1. **接入**：Webhook / SLS / Prometheus 等归一化为 Case。
2. **编排**：Skill 按步骤调度 Plugin Capability，经 MCP Gateway 调用工具。
3. **证据**：日志、链路、代码检索与图谱结果归集为 Evidence。
4. **根因**：RootCauseEngine 多假设推理；可选 LLM 增强报告文案。
5. **触达**：推送通知，并可在 Admin 中回放与审计。

---

## 快速开始

推荐 **Docker Compose** 一键启动完整栈（API、Admin、Worker、Scheduler、Zoekt、Qdrant、GitNexus）。  
部署包说明见 [docker/README.md](docker/README.md)。

### 1. 克隆并准备配置

```bash
git clone https://github.com/iceycn/root-seeker-v2.git
cd root-seeker-v2
cp .env.docker .env   # 按需填写 LLM / SLS 等；不配也可跑通基础能力
```

### 2. 启动

```bash
./start.sh            # 推荐：缺 Zoekt 二进制时会自动下载
# 或使用 Docker Hub 预构建镜像（账号 wuhun0301）：
# DOCKERHUB_USER=wuhun0301 ./start.sh --pull
# 或
make docker-up
docker compose up -d --build
```

### 3. 验证

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000/healthz | API 健康检查 |
| http://localhost:8000/docs | Swagger |
| http://localhost:8010/admin | 管理控制台 |
| http://localhost:6070 | Zoekt 搜索 |
| http://localhost:6071/healthz | Zoekt 远程索引 HTTP |
| http://localhost:6333 | Qdrant |
| http://localhost:7474/healthz | GitNexus sidecar |

```bash
curl http://localhost:8000/healthz
docker compose logs -f api
make docker-down
```

默认使用 SQLite + hash embedding，**无需外部 AI** 即可运行。需要 LLM 报告增强时，在 `.env` 配置 `ROOTSEEKER_LLM_*`。

---

## Hybrid 本地开发

适合本机改 Python 代码、索引服务仍跑在 Docker：

```powershell
# Windows
.\scripts\start-local.ps1
```

脚本会：

1. 启动 `zoekt` / `qdrant` / `gitnexus`（`docker-compose.hybrid.yml`，挂载 `./repos`）
2. 配置路径映射（本机 `repos` → 容器 `/repos`、`/data/repos`）
3. 在本机拉起 API `:8000` 与 Admin `:8010`

关键环境变量（`start-local.ps1` 已设置）：

| 变量 | 示例 |
| --- | --- |
| `ROOTSEEKER_ZOEKT_ENDPOINT` | `http://127.0.0.1:6070` |
| `ROOTSEEKER_ZOEKT_INDEX_ENDPOINT` | `http://127.0.0.1:6071` |
| `ROOTSEEKER_ZOEKT_PATH_MAP` | `<abs>/repos:/repos` |
| `ROOTSEEKER_GITNEXUS_ENDPOINT` | `http://127.0.0.1:7474` |
| `ROOTSEEKER_GITNEXUS_PATH_MAP` | `<abs>/repos:/data/repos` |
| `ROOTSEEKER_REPO_BASE_PATH` | `repos` |

仅重建索引侧车：

```powershell
.\scripts\start_gitnexus_docker.ps1
# 或
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up -d --build zoekt qdrant gitnexus
```

纯本地 Python（无 Docker 索引）时：

```bash
pip install -e ".[dev]"   # 或 make install
pytest                    # 或 make test
make demo                 # 本地端到端演示
```

---

## 常用命令

### 本地

| 命令 | 说明 |
| --- | --- |
| `make install` | 安装依赖 |
| `make test` | 全部测试 |
| `make demo` | 本地端到端演示 |
| `make api` / `make admin` | 启动 API / Admin |
| `make worker-loop` | Worker 轮询 |
| `make scheduler-loop` | Cron 轮询 |

### CLI

```bash
rootseeker demo
rootseeker replay
rootseeker-admin
rootseeker-worker --loop --interval-seconds 5
rootseeker-scheduler --loop --interval-seconds 60
```

### Docker

| 命令 | 说明 |
| --- | --- |
| `make docker-up` | 构建并启动全部服务 |
| `make docker-down` | 停止 |
| `make docker-logs` | API 日志 |
| `make docker-ps` | 容器状态 |

---

## API 与管理控制台

### API（`:8000`）

| 端点 | 说明 |
| --- | --- |
| `GET /healthz` · `GET /readyz` | 健康 / 就绪 |
| `GET /metrics` | Prometheus 指标 |
| `POST /cases/run-default` | 执行默认排查流程 |
| `GET /cases/{case_id}` · `/reports/{case_id}` · `/evidence/{case_id}` | Case / 报告 / 证据 |
| `POST /webhook/{channel}` | 告警接入 |
| `WebSocket /gateway/ws` | 控制平面 |

文档：http://localhost:8000/docs

### Admin（`:8010`）

访问：http://127.0.0.1:8010/admin

主要能力：

- Skills / Plugins / MCP 工具一览
- Git 仓库注册、同步、强制重建图谱
- **定时任务**（如每小时同步有变更仓库并重建 GitNexus）
- **错误排查助手**（粘贴日志触发默认 Flow）
- 服务目录、语义代码搜索、运行时与索引状态

---

## 代码索引

完整栈与 Hybrid 模式均通过 **容器内远程索引**，无需本机安装 `zoekt-index` / `gitnexus` CLI。

| 组件 | 端口 | 作用 |
| --- | --- | --- |
| Zoekt | 6070 搜索 · **6071 索引** | 词法代码搜索 / 远程 `zoekt-index` |
| Qdrant | 6333 | 语义向量检索 |
| GitNexus | 7474 | 知识图谱 analyze / 查询 sidecar |

仅启动索引服务：

```bash
docker compose up -d --build zoekt qdrant gitnexus
```

仓库克隆目录默认 `ROOTSEEKER_REPO_BASE_PATH=repos`。Hybrid 下请保证 `ROOTSEEKER_ZOEKT_PATH_MAP` / `ROOTSEEKER_GITNEXUS_PATH_MAP` 指向同一本机目录。

### Embedding

默认 `ROOTSEEKER_EMBEDDING_PROVIDER=hash`（本地确定性向量）。接入真实模型：

```bash
export ROOTSEEKER_EMBEDDING_PROVIDER=openai_compatible
export ROOTSEEKER_EMBEDDING_BASE_URL=https://api.openai.com/v1
export ROOTSEEKER_EMBEDDING_API_KEY=...
export ROOTSEEKER_EMBEDDING_MODEL=text-embedding-3-small
export ROOTSEEKER_EMBEDDING_DIMENSION=1536
```

---

## 配置说明

- Docker：以 [`.env.docker`](.env.docker) 为模板（`cp .env.docker .env`）
- 本地全量参考：[`.env.example`](.env.example)

### 常用变量

| 分组 | 变量 |
| --- | --- |
| 适配器 | `ROOTSEEKER_INTERNAL_ADAPTER_KIND`（默认 `composite`） |
| 存储 | `ROOTSEEKER_STORAGE_BACKEND=sqlite` · `ROOTSEEKER_SQLITE_DB_PATH` |
| Zoekt | `ROOTSEEKER_ZOEKT_ENDPOINT` · `ROOTSEEKER_ZOEKT_INDEX_ENDPOINT` · `ROOTSEEKER_ZOEKT_PATH_MAP` |
| Qdrant | `ROOTSEEKER_QDRANT_ENDPOINT` · `ROOTSEEKER_QDRANT_COLLECTION_NAME` |
| GitNexus | `ROOTSEEKER_GITNEXUS_ENDPOINT` · `ROOTSEEKER_GITNEXUS_PATH_MAP` |
| 仓库 | `ROOTSEEKER_REPO_BASE_PATH` · `ROOTSEEKER_REPO_ENABLE_*` |
| LLM | `ROOTSEEKER_LLM_BASE_URL` · `ROOTSEEKER_LLM_API_KEY` · `ROOTSEEKER_LLM_MODEL` |
| 日志/链路 | `SLS_*` · `JAEGER_ENDPOINT` |
| 代理 | `HTTP_PROXY` / `HTTPS_PROXY`（容器内会映射到 `host.docker.internal`；本机 hybrid 保持 `127.0.0.1`） |

可选 tracing profile：

```bash
docker compose --profile tracing up -d
```

---

## 项目结构

```
rootseeker/     # 核心运行时与业务模块
apps/           # api / admin / worker / scheduler / cli
skills/         # 内置与自定义 Skill
plugins/        # 内置与自定义 Plugin
mcp_servers/    # MCP 工具实现
docker/         # Zoekt / GitNexus 镜像与 sidecar
tests/          # 单元、集成与回放测试
scripts/        # 启动与联调脚本
docs/           # 架构与实现状态
k8s/            # Kubernetes 清单
```

---

## 模块状态

`Completed` 已实现并有测试 · `Partial` 已实现待加固 · `Planned` 未达目标深度

| 模块 | 状态 |
| --- | --- |
| 契约、存储/审计、Plugin / Skill / MCP | Completed |
| 服务目录、日志平面、代码索引（含远程 Zoekt / GitNexus） | Completed |
| 证据、根因、Task/Flow、默认排查 Flow | Completed |
| API / Admin / Worker / Scheduler / 定时仓库同步 | Completed |
| 渠道路由、Gateway、SQLite、LLM 报告增强 | Completed |
| Agent Runtime（LLM 工具规划、自修复） | Partial |
| 审批策略、部署策略编排 | Partial |

详情：[docs/implementation-status.md](docs/implementation-status.md)

---

## 相关文档

- [实现状态与缺口](docs/implementation-status.md)
- [Case 状态机](docs/architecture/case-state-machine.md)
- [状态机总览](docs/architecture/state-machines.md)

---

## 贡献指南

欢迎提交 Pull Request 或 Issue！

1. Fork 本仓库
2. 新建特性分支
3. 提交代码并确保测试通过
4. 新建 Pull Request

---

## License

MIT License © 2026 iceycn / RootSeeker Team

见 [LICENSE](LICENSE)。
```
