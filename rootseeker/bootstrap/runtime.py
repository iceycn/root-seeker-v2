from __future__ import annotations

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
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.mcp_plane import McpGateway, PolicyGuard, ToolRegistry
from rootseeker.observability.audit import InMemoryAuditLog
from rootseeker.plugin_system import ManifestRegistry, build_registry_from_bundled
from rootseeker.policies import ApprovalStore, WebhookApprovalEventSink
from rootseeker.service_catalog import MemoryServiceCatalog
from rootseeker.skill_system import SkillRegistry, build_registry_from_builtin_skills
from rootseeker.storage.memory import InMemoryCaseStore, InMemoryEvidenceStore, InMemoryReportStore
from rootseeker.storage.sqlite import SqliteCaseStore, SqliteEvidenceStore, SqliteReportStore
from rootseeker.storage.sqlite_checkpoint import SqliteCheckpointStore

if TYPE_CHECKING:
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
    case_store: InMemoryCaseStore | SqliteCaseStore
    evidence_store: InMemoryEvidenceStore | SqliteEvidenceStore
    report_store: InMemoryReportStore | SqliteReportStore
    flow_checkpoint_store: FlowCheckpointStore | SqliteCheckpointStore
    approval_store: ApprovalStore

    def run_default_flow_from_case_request(
        self,
        case_request: CaseCreateRequest,
        *,
        start_from_step_index: int = 0,
        prior_step_outputs: dict[str, dict[str, Any]] | None = None,
        prior_case_id: str | None = None,
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
        return result

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
    approval_event_sink = None
    if settings.approval_webhook_url:
        approval_event_sink = WebhookApprovalEventSink(
            settings.approval_webhook_url,
            timeout_seconds=settings.approval_webhook_timeout_seconds,
        )
    approval_store = ApprovalStore(event_sink=approval_event_sink)
    policy = PolicyGuard(
        deny_write=deny_write,
        approval_store=approval_store,
        require_approval_for_write=settings.approval_required_for_write_tools,
    )
    gateway = McpGateway(tools, policy, audit)
    case_store, evidence_store, report_store, flow_checkpoint_store = _build_storage(root, settings)
    return DevRuntime(
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
    )


def _build_storage(
    repo_root: Path,
    settings: RootSeekerSettings,
) -> tuple[
    InMemoryCaseStore | SqliteCaseStore,
    InMemoryEvidenceStore | SqliteEvidenceStore,
    InMemoryReportStore | SqliteReportStore,
    FlowCheckpointStore | SqliteCheckpointStore,
]:
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
