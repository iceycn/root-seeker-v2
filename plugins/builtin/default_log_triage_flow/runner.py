from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rootseeker.contracts.case import CaseCreateRequest, CaseRecord
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.report import CaseReport
from rootseeker.contracts.tool import ToolCallResult
from rootseeker.mcp_plane import McpGateway, ToolRegistry
from rootseeker.plugin_system.registry import ManifestRegistry
from rootseeker.skill_runtime.flow_executor import DEFAULT_FLOW_PLUGIN_ID, execute_skill_flow
from rootseeker.skill_system.registry import SkillRegistry

DEFAULT_FLOW_CAPABILITY_ID = "flow.builtin.default_log_triage"

__all__ = [
    "DEFAULT_FLOW_CAPABILITY_ID",
    "DEFAULT_FLOW_PLUGIN_ID",
    "DefaultFlowRunResult",
    "execute_default_log_triage_flow",
]


@dataclass
class DefaultFlowRunResult:
    case: CaseRecord
    evidence_pack: EvidencePack
    report: CaseReport
    tool_results: list[ToolCallResult]
    step_traces: list[dict[str, Any]] | None = None


def execute_default_log_triage_flow(
    *,
    case_request: CaseCreateRequest,
    skill_registry: SkillRegistry,
    plugin_registry: ManifestRegistry,
    gateway: McpGateway,
    tool_registry: ToolRegistry,
    start_from_step_index: int = 0,
    prior_step_outputs: dict[str, dict[str, Any]] | None = None,
    prior_case_id: str | None = None,
) -> DefaultFlowRunResult:
    _validate_default_flow_registration(plugin_registry)
    result = execute_skill_flow(
        case_request=case_request,
        skill_registry=skill_registry,
        tool_registry=tool_registry,
        gateway=gateway,
        start_from_step_index=start_from_step_index,
        prior_step_outputs=prior_step_outputs,
        prior_case_id=prior_case_id,
    )
    return DefaultFlowRunResult(
        case=result.case,
        evidence_pack=result.evidence_pack,
        report=result.report,
        tool_results=result.tool_results,
        step_traces=result.step_traces,
    )


def _validate_default_flow_registration(plugin_registry: ManifestRegistry) -> None:
    plugin = plugin_registry.get_plugin(DEFAULT_FLOW_PLUGIN_ID)
    if plugin is None:
        raise ValueError(f"Default flow plugin not found: {DEFAULT_FLOW_PLUGIN_ID}")
    cap = plugin_registry.resolve_capability(DEFAULT_FLOW_CAPABILITY_ID)
    if cap is None or cap.plugin_id != DEFAULT_FLOW_PLUGIN_ID:
        raise ValueError(f"Default flow capability missing: {DEFAULT_FLOW_CAPABILITY_ID}")
