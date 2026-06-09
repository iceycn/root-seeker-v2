# RootSeeker V2

RootSeeker V2 is an enterprise incident troubleshooting system for production log chains.

## Current Stage

MVP chain is runnable end-to-end in development runtime. Several platform modules are now
implemented beyond MVP, but some areas are still partial and need further production hardening.

## Module Status Matrix

Status legend:

- `Completed`: implemented and covered by current tests in this repo
- `Partial`: implemented with reduced scope or simpler defaults pending hardening
- `Planned`: not yet implemented to the target design depth

| Ability Package | Module | Status |
| --- | --- | --- |
| 0-2 | Skeleton, contracts, storage/audit | Completed |
| 3-5 | Plugin System, Skill System, MCP Plane (internal + external path) | Completed |
| 6-8 | Service Catalog, Log Data Plane, Code Index | Completed |
| 9-11 | Evidence, RootCauseEngine, Task/Flow Runtime | Completed |
| 12-13 | Default flow + API/Worker/Scheduler entrypoints | Completed |
| 14 | Replay/Evaluation + CLI/Cron replay | Completed |
| 7 | Agent Runtime baseline (run loop, LLM tool planning, self-repair attempts, tool traces, compaction) | Partial |
| 9 | Channel Routing (inbound/router/session/outbound/security + multi-channel normalizers) | Completed |
| 10 | Gateway Control Plane (protocol/server/method/subscription/broadcast + WebSocket + auth/rate-limit) | Completed |
| 13 | Infra/Observability advanced baseline (safe fs/json, network guard, secret resolver, redaction) | Completed |
| - | LLM report enhancement (OpenAI-compatible provider + fallback metadata) | Completed |
| - | Checkpoint step-level resume (step_outputs, execute_from_checkpoint) | Completed |
| - | Skill auto-synthesis (DraftBuilder/Reviewer/Publisher) | Completed |
| - | SQLite persistent storage (Case/Evidence/Report/Task/Checkpoint/Replay) | Completed |
| - | Multi-channel adapters (Webhook/Feishu/DingTalk/WeChat/Slack/Discord) | Completed |
| - | Approval policy baseline (write-tool approval store + gateway methods) | Partial |
| - | Deployment policy orchestration (quality gate + manual override decision) | Partial |

See `docs/implementation-status.md` for detailed scope and gaps.

## Quick Start

1. Create a Python 3.11+ environment.
2. Install project dependencies:

   ```bash
   pip install -e ".[dev]"
   ```

3. Run all tests:

   ```bash
   pytest
   ```

## Common Commands

```bash
make install
make test
make demo
make api
make admin
make demo-api
make worker
make worker-loop
make scheduler
make scheduler-loop
rootseeker demo
rootseeker replay
rootseeker-worker
rootseeker-scheduler
```

`rootseeker-worker` supports `--loop --interval-seconds --max-empty-polls --max-runs --seed-demo`.
`rootseeker-scheduler` supports `--loop --schedule --timezone --state-path --run-immediately/--no-run-immediately --interval-seconds --max-runs --retries --retry-delay-seconds`.

## Admin Console

RootSeeker V2 ships a standalone admin app, separate from the client/API service:

```bash
make admin
# or
ADMIN_PORT=8010 rootseeker-admin
# or
uvicorn apps.admin.main:app --host 127.0.0.1 --port 8010
```

Open `http://127.0.0.1:8010/admin`.

Current admin capabilities:

- View skills, plugins and registered MCP tools
- Register, unregister, sync and inspect repositories
- Trigger Zoekt/Qdrant indexing through the same repo tools used by the API
- View and update the in-memory service catalog
- Run Qdrant semantic code search
- Inspect runtime health and index status

Adapter switch (`composite` / `http`) via env:

```bash
export ROOTSEEKER_INTERNAL_ADAPTER_KIND=composite
export ROOTSEEKER_NOTIFY_DEFAULT_URL=https://example.com/my-webhook

export ROOTSEEKER_INTERNAL_ADAPTER_KIND=http
export ROOTSEEKER_INTERNAL_HTTP_BASE_URL=http://127.0.0.1:9000
export ROOTSEEKER_INTERNAL_HTTP_TIMEOUT_SECONDS=5
```

Persistent storage is opt-in. The default remains in-memory for local smoke tests:

```bash
export ROOTSEEKER_STORAGE_BACKEND=sqlite
export ROOTSEEKER_SQLITE_DB_PATH=data/rootseeker.db
```

Cron scheduler state is file-backed by default:

```bash
export ROOTSEEKER_CRON_STATE_PATH=data/cron/scheduler-state.json
rootseeker-scheduler --loop --schedule "*/5 * * * *"
```

LLM report enhancement uses an OpenAI-compatible chat completions endpoint. When these
variables are configured, the default troubleshooting flow enhances `CaseReport.summary`
and `CaseReport.root_cause` with model output while preserving the rule-engine result in
report metadata:

```bash
export ROOTSEEKER_LLM_BASE_URL=https://api.openai.com/v1
export ROOTSEEKER_LLM_API_KEY=...
export ROOTSEEKER_LLM_MODEL=gpt-4o-mini
# optional
export ROOTSEEKER_LLM_PROVIDER_NAME=openai
export ROOTSEEKER_LLM_ENABLED=false # opt out
```

## Run API Service

```bash
uvicorn apps.api.main:app --reload --port 8000
```

Useful endpoints:

- `GET /healthz` / `GET /readyz` - Runtime health and readiness checks
- `GET /metrics` - Prometheus text metrics
- `GET /skills` - List available skills
- `POST /cases/run-default` - Run default troubleshooting flow
- `GET /cases/{case_id}` - Get case details
- `GET /reports/{case_id}` - Get analysis report
- `GET /evidence/{case_id}` - Get evidence pack
- `GET /cases/{case_id}/audit` - Get audit trail
- `GET /flows/checkpoints` - List flow checkpoints
- `POST /webhook/{channel}` - External alert ingestion (webhook/aliyun/sls/prometheus)
- `WebSocket /gateway/ws` - Control-plane communication
- `GET /gateway/connections` - List active WebSocket connections

Approval workflow notifications are opt-in. When configured, approval request and decision
events are posted to the external endpoint while local approval state remains authoritative:

```bash
export ROOTSEEKER_APPROVAL_WEBHOOK_URL=https://example.com/approval-workflow
export ROOTSEEKER_APPROVAL_WEBHOOK_TIMEOUT_SECONDS=5
```

### API Documentation

FastAPI provides built-in interactive documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Run API End-to-End Demo

1. Start API server:

   ```bash
   make api
   ```

2. Run API demo in another terminal:

   ```bash
   make demo-api
   ```

The script will call health, skills, run-default, case query, and report query in sequence.

## Run End-to-End Demo

```bash
python scripts/demo_default_flow.py
```

The script will:

- build development runtime with builtin plugins/skills,
- run the default troubleshooting flow from an alert-like payload,
- print case/report/evidence/audit summary.

## Default Execution Chain

```mermaid
flowchart LR
  A[Case] --> B[Skill]
  B --> C[Step]
  C --> D[Plugin Capability]
  D --> E[MCP ToolCall]
  E --> F[Tool Result]
  F --> G[Evidence]
  G --> H[RootCauseEngine]
  H --> I[CaseReport]
```

## Project Layout

- `rootseeker/`: core runtime and business modules
- `apps/`: app entrypoints (api, worker, scheduler, cli)
- `skills/`: builtin and custom skills
- `plugins/`: builtin and custom plugins
- `mcp_servers/`: internal and external MCP tool implementations
- `tests/`: unit, integration, and replay tests
- `scripts/`: runnable helper scripts

## Zoekt + Qdrant（无 Docker，推荐本机开发）

不依赖容器，使用仓库内 `config/qdrant_config.yaml`，数据目录在 `./data/`。

1. **安装 Zoekt（需 Go）**

   ```bash
   go install github.com/sourcegraph/zoekt/cmd/zoekt-webserver@latest
   go install github.com/sourcegraph/zoekt/cmd/zoekt-index@latest
   export PATH="$(go env GOPATH)/bin:$PATH"
   ```

2. **安装 Qdrant 二进制**  
   从 [Qdrant Releases](https://github.com/qdrant/qdrant/releases) 下载对应平台，将可执行文件命名为 `qdrant` 并加入 `PATH`，或放到 `tools/qdrant/qdrant`，或通过 `export ROOTSEEKER_QDRANT_BINARY=/绝对路径/qdrant`。

3. **启动与联调**

   ```bash
   ./scripts/install_local_codesearch_deps.sh # 检查/安装 Zoekt，提示安装 Qdrant
   ./scripts/start_zoekt_qdrant.sh          # 后台启动，日志见 data/run/*.log
   ./scripts/run_real_codesearch_smoke.sh   # 本地示例仓 + Zoekt/Qdrant + API repo sync + 语义搜索
   ./scripts/stop_zoekt_qdrant.sh           # 停止本机 pid 方式拉起的进程
   ```

4. **Embedding 配置**

   默认 `ROOTSEEKER_EMBEDDING_PROVIDER=hash`，使用本地 deterministic 向量，适合无外部服务的真实 Qdrant 写入/查询链路。需要接真实 embedding 服务时，设置：

   ```bash
   export ROOTSEEKER_EMBEDDING_PROVIDER=openai_compatible
   export ROOTSEEKER_EMBEDDING_BASE_URL=https://api.openai.com/v1
   export ROOTSEEKER_EMBEDDING_API_KEY=...
   export ROOTSEEKER_EMBEDDING_MODEL=text-embedding-3-small
   export ROOTSEEKER_EMBEDDING_DIMENSION=1536
   ```

5. **仅用 Docker 的用户**（可选）见下方 `start_zoekt_qdrant_docker.sh`。

## Docker Deployment

### Quick Start with Docker Compose

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your configuration
# Then start all services
docker compose up -d

# View logs
docker compose logs -f api

# Stop services
docker compose down
```

### Available Services

| Service | Port | Description |
|---------|------|-------------|
| api | 8000 | REST API server |
| worker | - | Background task processor |
| scheduler | - | Cron job scheduler |
| jaeger | 16686 | Trace visualization (optional) |
| zoekt | 6070 | 词法检索，`docker/Dockerfile.zoekt` 构建（`zoekt-webserver -rpc`，同 root_seek） |
| qdrant | 6333 (gRPC 6334) | 向量库，`qdrant/qdrant:v1.16.3`（与 root_seek Docker 编排一致） |

### Optional Services

```bash
# Start with Jaeger tracing
docker compose --profile tracing up -d

# Zoekt + Qdrant（Docker 可选；无 Docker 时用本机二进制，见上文「无 Docker」小节）
docker compose --profile codesearch up -d --build zoekt qdrant

# 本机二进制启动（无 Docker）
./scripts/start_zoekt_qdrant.sh

# 仅当使用 Docker Compose 起索引服务时：
# ./scripts/start_zoekt_qdrant_docker.sh

# 一键真实联调（本机 zoekt-index + 探测；不调用 Docker）
./scripts/run_real_codesearch_smoke.sh

# Start all services
docker compose --profile tracing --profile codesearch up -d
```

### Environment Variables

See `.env.example` for all available configuration options. Key variables:

| Variable | Description |
|----------|-------------|
| `ROOTSEEKER_INTERNAL_ADAPTER_KIND` | `composite` (default: SLS/Jaeger/Zoekt + RepoSync), `http` (delegate internal tools to `ROOTSEEKER_INTERNAL_HTTP_BASE_URL`) |
| `ROOTSEEKER_NOTIFY_DEFAULT_URL` | Webhook URL for `notify.send` when using composite (optional; skips send if unset) |
| `ZOEKT_ENDPOINT` / `ROOTSEEKER_ZOEKT_ENDPOINT` | Zoekt HTTP API (`root_seek`: `zoekt.api_base_url`, e.g. `http://127.0.0.1:6070`) |
| `QDRANT_ENDPOINT` / `ROOTSEEKER_QDRANT_ENDPOINT` | Qdrant REST (`root_seek`: `qdrant.url`) |
| `QDRANT_COLLECTION_NAME` / `ROOTSEEKER_QDRANT_COLLECTION_NAME` | Vector collection (`root_seek`: `qdrant.collection`, default `code_chunks`) |
| `QDRANT_API_KEY` / `ROOTSEEKER_QDRANT_API_KEY` | Optional; Qdrant Cloud (`root_seek`: `qdrant.api_key`) |
| `ROOTSEEKER_ZOEKT_INDEX_DIR` | Local zoekt-index output dir, default `data/zoekt/index` |
| `ROOTSEEKER_ZOEKT_WEBSERVER` / `ROOTSEEKER_ZOEKT_INDEX_BINARY` | Optional explicit local Zoekt binaries |
| `ROOTSEEKER_QDRANT_BINARY` | Optional explicit local Qdrant binary |
| `ROOTSEEKER_EMBEDDING_PROVIDER` | `hash` (default) or `openai_compatible` / `http` |
| `ROOTSEEKER_EMBEDDING_*` | Embedding dimension, base URL, API key, model and timeout |
| `SLS_*` | Alibaba Cloud SLS configuration |
| `JAEGER_ENDPOINT` | Jaeger API endpoint |
