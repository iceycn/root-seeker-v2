# RootSeeker V2 Implementation Status

This document tracks the current implementation scope to keep blueprint expectations and
repository behavior aligned.

## Completed

- Default troubleshooting chain:
  - `Case -> Skill -> Step -> Plugin Capability -> MCP ToolCall -> Evidence -> RootCauseEngine -> CaseReport -> notify`
- Builtin plugin + skill loading and registration
- MCP internal gateway with policy + audit
- MCP external path (`ToolScope.EXTERNAL`) through unified `McpGateway`
- Gateway control-plane:
  - protocol frames, method registry, server request handling, subscriptions, broadcaster
  - **WebSocket transport layer** with heartbeat, connection lifecycle, topic subscription, request dispatch
  - **Business methods**: case.create/get/list/resume, flow.run/resume/step/checkpoints, skill.list/get, tool.invoke/list
  - **Authentication/Authorization/Rate limit primitives**: TokenAuthProvider, Authorizer and token bucket are implemented; GatewayServer supports optional injection
- Channel routing:
  - inbound normalize, session key, route resolve, outbound target and send, security checks
  - **Multi-channel normalizers**: aliyun, sls, prometheus, webhook
  - **ChannelAdapter/ChannelRegistry**: pluggable outbound notification adapters
  - **Multi-channel adapters**: Webhook, Feishu, DingTalk, WeChat Work, Slack, Discord
- Task runtime unified for `CASE_RUN`, `CRON`, `REPLAY`, `FLOW_RESUME`, `FLOW_STEP`
- **Checkpoint step-level resume**:
  - `step_outputs` stored in checkpoint payload
  - `FlowExecutor.execute_from_checkpoint` for step-level recovery
  - `resume_status` tracking (`resumed_from_step`, `replayed`, `skipped_completed`)
- **RootCauseEngine enhanced reasoning**:
  - Multi-hypothesis generation with pattern matching
  - Hypothesis validation with support/contradiction counting
  - Evidence weighting by type/recency/relevance
  - Convergence checking for analysis termination
- **LLM report enhancement**:
  - OpenAI-compatible chat completions client
  - Config-driven provider/model selection
  - Rule-engine fallback and LLM metadata preservation in reports
- **Skill auto-synthesis**:
  - `SkillDraftBuilder` generates skill drafts from case reports
  - `SkillReviewer` reviews and approves drafts
  - `SkillPublisher` publishes approved skills
- API query loop:
  - case/report/evidence/audit retrieval after run-default
  - **Webhook endpoints**: `POST /webhook/{channel}` for external alert ingestion
  - **Gateway WebSocket**: `/gateway/ws` for control-plane communication
- Infra/observability baseline:
  - safe path guard, atomic json store, network guard, exec approval, event bus, agent event builder
  - secret resolver (`env`, `file`, `exec`)
  - redaction + structured logging + diagnostic collector
  - enhanced runtime health snapshots and Prometheus text metrics endpoints
  - Prometheus runtime activity metrics for audit actions, agent/MCP tool events and approval status
- **SQLite persistent storage**:
  - `SqliteCaseStore`, `SqliteEvidenceStore`, `SqliteReportStore`
  - `SqliteTaskStore`, `SqliteCheckpointStore`, `SqliteReplayStore`
  - Full CRUD operations with proper serialization
  - Default dev/runtime wiring still uses in-memory stores unless explicitly injected by integration code
- **Production-grade external adapters**:
  - `SlsLogAdapter`: Alibaba Cloud SLS log queries with API signature
  - `JaegerTraceAdapter`: Jaeger trace chain retrieval
  - `ZoektCodeAdapter`: Zoekt code search and file reading
  - `CompositeProductionAdapter`: Unified adapter combining all external services
  - Environment-based configuration; composite adapter fails fast when SLS/Jaeger/Zoekt
    or required notify endpoints are missing (no silent placeholder data).
- **Code Index**:
  - `RepoSyncService`: Git clone/pull, file scan, chunking, Zoekt CLI index and Qdrant vector upsert
  - `ZoektIndexer`: local `zoekt-index` CLI indexing and `/api/list` status
  - `QdrantIndexer`: vector collection management, repo cleanup, chunk upsert and semantic search
  - `LspClient` / `LspToolsService`: references, definitions, hover and symbols exposed through MCP tools
  - REST API: `/repos`, `/repos/{name}/sync` for repository management
- **Replay/Evaluation quality gate**:
  - Replay runner computes aggregate metrics and stores run snapshots
  - Quality gate supports configurable policy thresholds
  - Evaluation reports expose `gate_policy_name` and `release_allowed`
- **Approval / policy orchestration baseline**:
  - `ApprovalStore` tracks pending/approved/rejected tool approvals
  - Approval lifecycle events can be published to an external webhook sink
  - `PolicyGuard` can require approval for write/admin MCP tools
  - `McpGateway` returns retryable `APPROVAL_REQUIRED` errors with approval metadata
  - Gateway control-plane methods expose `approval.list/get/approve/reject`
- **Deployment policy orchestration**:
  - `DeploymentPolicyOrchestrator` combines evaluation reports and manual override approvals
  - Blocking quality gates can create `release.deploy` approval requests
  - CRON/REPLAY tasks persist `deployment_decision` and `report_release_allowed`
- **Test coverage**:
  - Unit tests for all core modules (contracts, storage, channel_routing, gateway, etc.)
  - Integration tests for default flow and API endpoints
  - E2E tests covering webhook → case → skill → evidence → report → notify chain

## Partial

- Service catalog data plane uses in-memory catalog by default (can be extended to external service registry)
- Agent Runtime now has a real run-loop baseline with attempt snapshots, prompt snapshots,
  model-route metadata, streaming run events, tool execution traces and context compaction. When
  an OpenAI-compatible LLM is configured, attempts can ask the model for a validated JSON tool plan
  and then execute that plan through `McpGateway`; invalid or failed plans fall back to the
  deterministic default flow on the final attempt. Failed planner attempts feed a compact history
  summary into the next attempt so the model can self-repair. Tool plans now carry execution
  metadata such as dependencies, timeout hints and required/non-critical calls; sequential execution
  skips downstream steps when required dependencies fail, while non-critical failures do not block
  dependent required work. Dependency-aware scheduling batches independent ready steps and can run
  each batch concurrently through `ToolCallLoop`; production-grade timeout/cancellation handling
  remains future hardening.
- Release governance has replay quality-gate decisions, write-tool approvals, deployment-policy
  decisions and webhook approval notifications. Richer bidirectional human-workflow integrations
  remain future hardening.

## Planned

- Richer bidirectional human-workflow integrations for approvals
- Docker Compose baseline exists; Kubernetes manifests and production hardening remain planned
- Deeper production health probes, SLO dashboards and alert rules

## Notes

- Skill frontmatter YAML must keep valid indentation; invalid frontmatter will break skill loading at import time.
- README status matrix should be updated whenever this document changes.
- External adapters require environment variables to be set for production use (see `mcp_servers/external/`).
