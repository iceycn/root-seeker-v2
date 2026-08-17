from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mcp_servers.internal.adapters import InternalToolAdapter
from mcp_servers.internal.handlers import register_internal_tools
from plugins.builtin.default_log_triage_flow import (
    DefaultFlowRunResult,
    execute_default_log_triage_flow,
)
from rootseeker.channel_routing import webhook_payload_to_case_create
from rootseeker.code_index.repo_sync import RepoSyncService
from rootseeker.config import build_internal_adapter_from_settings
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.infra_core import EventBus, ExecApprovalGuard, NetworkGuard, PresenceRegistry, RootSeekerSettings
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog
from rootseeker.plugin_system import ManifestRegistry, build_registry_from_bundled
from rootseeker.policies import ApprovalStore, WebhookApprovalEventSink
from rootseeker.replay.store import ReplayStore
from rootseeker.skill_system import SkillRegistry, build_registry_from_builtin_skills
from rootseeker.storage.memory import InMemoryCaseStore, InMemoryEvidenceStore, InMemoryReportStore
from rootseeker.storage.mysql import MysqlCaseStore, MysqlEvidenceStore, MysqlReportStore
from rootseeker.storage.mysql_checkpoint import MysqlCheckpointStore
from rootseeker.storage.mysql_conn import mysql_config_from_settings
from rootseeker.storage.sqlite import SqliteCaseStore, SqliteEvidenceStore, SqliteReportStore
from rootseeker.service_catalog import MemoryServiceCatalog
from rootseeker.storage.sqlite_checkpoint import SqliteCheckpointStore

if TYPE_CHECKING:
    from rootseeker.agent_runtime.result import AgentRunResult
    from rootseeker.flow_runtime.checkpoint import FlowCheckpointStore

__all__ = ["DevRuntime", "create_dev_runtime"]


@dataclass
class DevRuntime:
    repo_root: Path
    audit_log: InMemoryAuditLog
    plugin_registry: ManifestRegistry
    skill_registry: SkillRegistry
    tool_registry: ToolRegistry
    service_catalog: MemoryServiceCatalog
    policy: PolicyGuard
    gateway: McpGateway
    case_store: InMemoryCaseStore | SqliteCaseStore | MysqlCaseStore
    evidence_store: InMemoryEvidenceStore | SqliteEvidenceStore | MysqlEvidenceStore
    report_store: InMemoryReportStore | SqliteReportStore | MysqlReportStore
    flow_checkpoint_store: FlowCheckpointStore | SqliteCheckpointStore | MysqlCheckpointStore
    approval_store: ApprovalStore
    replay_store: ReplayStore
    network_guard: NetworkGuard
    exec_approval_guard: ExecApprovalGuard
    event_bus: EventBus
    presence_registry: PresenceRegistry
    node_id: str
    agent_flow_enabled: bool = False

    def heartbeat_presence(
        self,
        role: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.presence_registry.heartbeat(
            node_id=self.node_id,
            role=role,
            metadata=metadata,
        )

    def resolve_use_agent(self, use_agent: bool | None = None) -> bool:
        if use_agent is not None:
            return use_agent
        return self.agent_flow_enabled

    def publish_case_completed(
        self,
        case_id: str,
        status: str,
        *,
        service_name: str,
        source: str,
        evidence_count: int,
        runner: str = "default_flow",
    ) -> None:
        self.event_bus.publish(
            "case.completed",
            {
                "case_id": case_id,
                "status": status,
                "service_name": service_name,
                "source": source,
                "evidence_count": evidence_count,
                "runner": runner,
            },
        )

    def run_agent_from_case_request(self, case_request: CaseCreateRequest) -> AgentRunResult:
        from rootseeker.agent_runtime import AgentRuntime

        result = AgentRuntime(self).run_case_detailed(case_request)
        case = self.case_store.get(result.case_id)
        pack = self.evidence_store.get_pack(result.case_id)
        if case is not None:
            self.publish_case_completed(
                result.case_id,
                result.status,
                service_name=case.service_name,
                source=case.source,
                evidence_count=len(pack.items) if pack is not None else 0,
                runner="agent",
            )
        return result

    def run_case_from_request(
        self,
        case_request: CaseCreateRequest,
        *,
        use_agent: bool | None = None,
        start_from_step_index: int = 0,
        prior_step_outputs: dict[str, dict[str, Any]] | None = None,
        prior_case_id: str | None = None,
    ) -> DefaultFlowRunResult | AgentRunResult:
        if self.resolve_use_agent(use_agent):
            return self.run_agent_from_case_request(case_request)
        return self.run_default_flow_from_case_request(
            case_request,
            start_from_step_index=start_from_step_index,
            prior_step_outputs=prior_step_outputs,
            prior_case_id=prior_case_id,
        )

    def run_default_flow_from_case_request(
        self,
        case_request: CaseCreateRequest,
        *,
        start_from_step_index: int = 0,
        prior_step_outputs: dict[str, dict[str, Any]] | None = None,
        prior_case_id: str | None = None,
        publish_completion: bool = True,
    ) -> DefaultFlowRunResult:
        result = execute_default_log_triage_flow(
            case_request=case_request,
            skill_registry=self.skill_registry,
            plugin_registry=self.plugin_registry,
            gateway=self.gateway,
            tool_registry=self.tool_registry,
            start_from_step_index=start_from_step_index,
            prior_step_outputs=prior_step_outputs,
            prior_case_id=prior_case_id,
        )
        self.case_store.put(result.case)
        self.evidence_store.put_pack(result.evidence_pack)
        self.report_store.put(result.report)
        if publish_completion:
            self.publish_case_completed(
                result.case.case_id,
                result.case.status.value,
                service_name=result.case.service_name,
                source=result.case.source,
                evidence_count=len(result.evidence_pack.items),
            )
        return result

    def _resolve_use_agent_from_payload(
        self,
        payload: dict[str, Any],
        case_request: CaseCreateRequest,
    ) -> bool | None:
        if payload.get("use_agent"):
            return True
        if case_request.metadata.get("use_agent"):
            return True
        return None

    def run_flow_from_case_request(
        self,
        case_request: CaseCreateRequest,
        *,
        use_agent: bool | None = None,
        **kwargs: Any,
    ) -> DefaultFlowRunResult | AgentRunResult:
        resolved = use_agent
        if resolved is None and "use_agent" in case_request.metadata:
            resolved = bool(case_request.metadata["use_agent"])
        return self.run_case_from_request(case_request, use_agent=resolved, **kwargs)

    def run_flow_from_payload(
        self,
        payload: dict[str, Any],
    ) -> DefaultFlowRunResult | AgentRunResult:
        case_request = webhook_payload_to_case_create(payload)
        return self.run_flow_from_case_request(
            case_request,
            use_agent=self._resolve_use_agent_from_payload(payload, case_request),
        )

    def run_default_flow_from_payload(self, payload: dict) -> DefaultFlowRunResult:
        case_request = webhook_payload_to_case_create(payload)
        return self.run_default_flow_from_case_request(case_request)


def create_dev_runtime(
    repo_root: Path | None = None,
    *,
    deny_write: bool = False,
    catalog: MemoryServiceCatalog | None = None,
    internal_adapter: InternalToolAdapter | None = None,
    repo_sync_service: RepoSyncService | None = None,
    node_role: str | None = None,
) -> DevRuntime:
    """Wire bundled plugins, builtin skills, internal tools, and gateway (dev/smoke)."""

    root = repo_root if repo_root is not None else Path.cwd()
    audit = InMemoryAuditLog()
    plugins = build_registry_from_bundled(root / "plugins" / "builtin")
    skills = build_registry_from_builtin_skills(root / "skills" / "builtin")
    tools = ToolRegistry()
    settings = RootSeekerSettings()
    adapter = internal_adapter or build_internal_adapter_from_settings(
        settings,
        catalog=catalog,
        repo_sync_service=repo_sync_service,
    )
    mem_cat = register_internal_tools(tools, adapter=adapter)
    network_guard = NetworkGuard(allow_private=settings.network_guard_allow_private)
    exec_approval_guard = ExecApprovalGuard(
        deny_all=settings.exec_approval_deny_all,
        allow_patterns=_parse_allow_patterns(settings.exec_approval_allow_patterns),
    )
    approval_event_sink = None
    if settings.approval_webhook_url:
        approval_event_sink = WebhookApprovalEventSink(
            settings.approval_webhook_url,
            timeout_seconds=settings.approval_webhook_timeout_seconds,
            network_guard=network_guard,
        )
    approval_store = ApprovalStore(event_sink=approval_event_sink)
    policy = PolicyGuard(
        deny_write=deny_write,
        approval_store=approval_store,
        require_approval_for_write=settings.approval_required_for_write_tools,
    )
    gateway = McpGateway(tools, policy, audit)
    case_store, evidence_store, report_store, flow_checkpoint_store = _build_storage(root, settings)
    replay_store = _build_replay_store(root, settings)
    event_bus = EventBus()
    presence_registry = PresenceRegistry()
    node_id = _resolve_node_id(settings)
    runtime = DevRuntime(
        repo_root=root,
        audit_log=audit,
        plugin_registry=plugins,
        skill_registry=skills,
        tool_registry=tools,
        service_catalog=mem_cat,
        policy=policy,
        gateway=gateway,
        case_store=case_store,
        evidence_store=evidence_store,
        report_store=report_store,
        flow_checkpoint_store=flow_checkpoint_store,
        approval_store=approval_store,
        replay_store=replay_store,
        network_guard=network_guard,
        exec_approval_guard=exec_approval_guard,
        agent_flow_enabled=settings.agent_flow_enabled,
        event_bus=event_bus,
        presence_registry=presence_registry,
        node_id=node_id,
    )
    resolved_role = node_role if node_role is not None else settings.node_role
    if resolved_role:
        runtime.heartbeat_presence(resolved_role)
    return runtime


def _resolve_node_id(settings: RootSeekerSettings) -> str:
    configured = (settings.node_id or "").strip()
    if configured:
        return configured
    return f"{socket.gethostname()}-{os.getpid()}"


def _build_storage(
    repo_root: Path,
    settings: RootSeekerSettings,
) -> tuple[
    InMemoryCaseStore | SqliteCaseStore | MysqlCaseStore,
    InMemoryEvidenceStore | SqliteEvidenceStore | MysqlEvidenceStore,
    InMemoryReportStore | SqliteReportStore | MysqlReportStore,
    FlowCheckpointStore | SqliteCheckpointStore | MysqlCheckpointStore,
]:
    if settings.storage_backend == "mysql":
        mysql = mysql_config_from_settings(settings)
        return (
            MysqlCaseStore(mysql),
            MysqlEvidenceStore(mysql),
            MysqlReportStore(mysql),
            MysqlCheckpointStore(mysql),
        )

    if settings.storage_backend == "sqlite":
        db_path = Path(settings.sqlite_db_path)
        if not db_path.is_absolute():
            db_path = repo_root / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return (
            SqliteCaseStore(db_path),
            SqliteEvidenceStore(db_path),
            SqliteReportStore(db_path),
            SqliteCheckpointStore(db_path),
        )

    from rootseeker.flow_runtime.checkpoint import FlowCheckpointStore

    return (
        InMemoryCaseStore(),
        InMemoryEvidenceStore(),
        InMemoryReportStore(),
        FlowCheckpointStore(),
    )


def _build_replay_store(repo_root: Path, settings: RootSeekerSettings) -> ReplayStore:
    if settings.storage_backend == "mysql":
        from rootseeker.storage.mysql_replay_history import MysqlReplayHistoryStore

        return MysqlReplayHistoryStore(mysql_config_from_settings(settings))
    if settings.storage_backend == "sqlite":
        from rootseeker.storage.sqlite_replay_history import SqliteReplayHistoryStore

        db_path = Path(settings.sqlite_db_path)
        if not db_path.is_absolute():
            db_path = repo_root / db_path
        return SqliteReplayHistoryStore(db_path)
    return ReplayStore()


def _parse_allow_patterns(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]
