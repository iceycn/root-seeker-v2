from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rootseeker.analysis import build_case_report
from rootseeker.contracts.case import (
    CaseCreateRequest,
    CaseRecord,
    CaseStatus,
    CaseStep,
    StepStatus,
)
from rootseeker.contracts.common import new_id, utc_now
from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.contracts.log_query import LogQueryResult
from rootseeker.contracts.report import CaseReport
from rootseeker.contracts.tool import ToolCallRequest, ToolCallResult
from rootseeker.evidence import append_log_query_evidence, append_tool_json_evidence
from rootseeker.mcp_plane import McpGateway
from rootseeker.plugin_system.registry import ManifestRegistry
from rootseeker.skill_system.registry import SkillRegistry, get_default_log_triage_skill

DEFAULT_FLOW_PLUGIN_ID = "builtin.default_log_triage_flow"
DEFAULT_FLOW_CAPABILITY_ID = "flow.builtin.default_log_triage"


@dataclass
class DefaultFlowRunResult:
    case: CaseRecord
    evidence_pack: EvidencePack
    report: CaseReport
    tool_results: list[ToolCallResult]


def execute_default_log_triage_flow(
    *,
    case_request: CaseCreateRequest,
    skill_registry: SkillRegistry,
    plugin_registry: ManifestRegistry,
    gateway: McpGateway,
    start_from_step_index: int = 0,
    prior_step_outputs: dict[str, dict[str, Any]] | None = None,
    prior_case_id: str | None = None,
) -> DefaultFlowRunResult:
    """Run default flow via Skill->Plugin capability->MCP tools chain.

    Args:
        case_request: The case creation request.
        skill_registry: Skill registry for loading skill definitions.
        plugin_registry: Plugin registry for capability resolution.
        gateway: MCP gateway for tool invocation.
        start_from_step_index: Index of the first step to execute (for resume).
        prior_step_outputs: Outputs from previously completed steps (for resume).
        prior_case_id: Existing case_id to reuse (for resume).
    """

    _validate_default_flow_registration(plugin_registry)
    skill = get_default_log_triage_skill(skill_registry)

    case_id = prior_case_id or new_id("case-")
    case = CaseRecord(
        case_id=case_id,
        title=case_request.title,
        symptom=case_request.symptom,
        service_name=case_request.service_name,
        source=case_request.source,
        status=CaseStatus.RUNNING,
        selected_skills=[skill.slug],
        metadata=dict(case_request.metadata),
    )
    case.steps = [
        CaseStep(
            step_id=step.step_id,
            name=step.name,
            skill_name=skill.slug,
            action=step.action,
            status=StepStatus.PENDING,
            tool_name=step.action,
        )
        for step in skill.steps
    ]

    # Restore prior step outputs and mark completed steps
    prior_outputs = prior_step_outputs or {}
    for idx, step in enumerate(case.steps):
        if idx < start_from_step_index:
            step.status = StepStatus.COMPLETED
            if step.step_id in prior_outputs:
                step.outputs = dict(prior_outputs[step.step_id])

    pack = EvidencePack(case_id=case.case_id, summary="default flow evidence")
    tool_results: list[ToolCallResult] = []
    notify_step: CaseStep | None = None
    step_outputs = dict(prior_outputs)

    for step in case.steps:
        if step.status == StepStatus.COMPLETED:
            # Skip already completed steps, but still map to evidence
            if step.step_id in prior_outputs:
                _map_result_to_evidence(pack=pack, action=step.action, content=prior_outputs[step.step_id])
            continue
        if step.action == "notify.send":
            notify_step = step
            continue
        step.status = StepStatus.RUNNING
        args = _build_step_args(step.action, case_request, step_outputs=step_outputs)
        skip_reason = args.pop("_skip_reason", None)
        if skip_reason:
            result = ToolCallResult(
                ok=True,
                tool_name=step.action,
                content={"skipped": True, "reason": skip_reason},
            )
            tool_results.append(result)
            step.outputs = dict(result.content)
            step_outputs[step.step_id] = dict(result.content)
            step.status = StepStatus.COMPLETED
            _map_result_to_evidence(pack=pack, action=step.action, content=result.content)
            continue
        req = ToolCallRequest(
            case_id=case.case_id,
            step_id=step.step_id,
            skill_name=skill.slug,
            tool_name=step.action,
            arguments=args,
        )
        result = gateway.invoke(req, plugin_id=DEFAULT_FLOW_PLUGIN_ID, actor="default-flow-plugin")
        tool_results.append(result)
        step.outputs = dict(result.content)
        if result.ok:
            step_outputs[step.step_id] = dict(result.content)
            step.status = StepStatus.COMPLETED
            _map_result_to_evidence(pack=pack, action=step.action, content=result.content)
        else:
            step.status = StepStatus.FAILED
            case.status = CaseStatus.FAILED
            break

    if case.status != CaseStatus.FAILED and notify_step is not None:
        notify_step.status = StepStatus.RUNNING
        report = build_case_report(case_id=case.case_id, title=case.title, pack=pack)
        notify_req = ToolCallRequest(
            case_id=case.case_id,
            step_id=notify_step.step_id,
            skill_name=skill.slug,
            tool_name=notify_step.action,
            arguments=_build_notify_args(case_request=case_request, report=report),
        )
        notify_result = gateway.invoke(
            notify_req,
            plugin_id=DEFAULT_FLOW_PLUGIN_ID,
            actor="default-flow-plugin",
        )
        tool_results.append(notify_result)
        notify_step.outputs = dict(notify_result.content)
        if notify_result.ok:
            notify_step.status = StepStatus.COMPLETED
            case.status = CaseStatus.COMPLETED
        else:
            notify_step.status = StepStatus.FAILED
            case.status = CaseStatus.FAILED
        case.updated_at = utc_now()
        return DefaultFlowRunResult(
            case=case,
            evidence_pack=pack,
            report=report,
            tool_results=tool_results,
        )

    if case.status != CaseStatus.FAILED:
        case.status = CaseStatus.COMPLETED
    case.updated_at = utc_now()
    report = build_case_report(case_id=case.case_id, title=case.title, pack=pack)
    return DefaultFlowRunResult(case=case, evidence_pack=pack, report=report, tool_results=tool_results)


def _validate_default_flow_registration(plugin_registry: ManifestRegistry) -> None:
    plugin = plugin_registry.get_plugin(DEFAULT_FLOW_PLUGIN_ID)
    if plugin is None:
        raise ValueError(f"Default flow plugin not found: {DEFAULT_FLOW_PLUGIN_ID}")
    cap = plugin_registry.resolve_capability(DEFAULT_FLOW_CAPABILITY_ID)
    if cap is None or cap.plugin_id != DEFAULT_FLOW_PLUGIN_ID:
        raise ValueError(f"Default flow capability missing: {DEFAULT_FLOW_CAPABILITY_ID}")


def _build_step_args(
    action: str,
    case_request: CaseCreateRequest,
    *,
    step_outputs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    outputs = step_outputs or {}
    normalized_case = _normalized_case_request(outputs)
    metadata = dict(case_request.metadata)
    normalized_metadata = normalized_case.get("metadata")
    if isinstance(normalized_metadata, dict):
        metadata.update(normalized_metadata)
    service_name = str(normalized_case.get("service_name") or case_request.service_name)
    symptom = str(normalized_case.get("symptom") or case_request.symptom)
    trace_id = str(metadata.get("trace_id", "trace-unknown"))
    tenant = str(metadata.get("tenant", "demo"))
    environment = str(metadata.get("environment", "prod"))
    if action == "incident.normalize":
        payload = {
            **metadata,
            "title": case_request.title,
            "service_name": case_request.service_name,
            "message": case_request.symptom,
            "source": case_request.source,
        }
        return {"payload": payload}
    if action == "catalog.resolve_service":
        return {
            "tenant": tenant,
            "environment": environment,
            "service_name": service_name,
        }
    if action == "catalog.get_log_sources":
        return {
            "tenant": tenant,
            "environment": environment,
            "service_name": service_name,
        }
    if action == "log.query_by_trace_id":
        return {"trace_id": trace_id, "service_name": service_name}
    if action == "log.query_by_template":
        return {"template_id": "default.error_window", "service_name": service_name}
    if action == "trace.get_chain":
        return {"trace_id": trace_id}
    if action == "code.search":
        return {"query": symptom}
    if action == "code.read":
        path = (
            _path_from_code_search(outputs)
            or metadata.get("code_path")
            or _path_from_normalized_input(outputs)
            or _path_from_symptom(symptom)
        )
        if not path:
            return {"_skip_reason": "No code search hit, explicit code_path, or file path in symptom."}
        return {"path": path}
    if action == "index.get_status":
        return {}
    if action == "repo.list":
        return {}
    return {}


def _normalized_case_request(step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    value = step_outputs.get("normalize-incident", {}).get("case_request")
    return value if isinstance(value, dict) else {}


def _path_from_normalized_input(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    extracted = step_outputs.get("normalize-incident", {}).get("extracted")
    if isinstance(extracted, dict) and extracted.get("code_path"):
        return str(extracted["code_path"])
    return None


def _path_from_code_search(step_outputs: dict[str, dict[str, Any]]) -> str | None:
    hits = step_outputs.get("code-search", {}).get("hits")
    if not isinstance(hits, list):
        return None
    for hit in hits:
        if isinstance(hit, dict) and hit.get("path"):
            return str(hit["path"])
    return None


def _path_from_symptom(symptom: str) -> str | None:
    match = re.search(r"([A-Za-z0-9_./-]+\.(?:java|kt|py|go|ts|tsx|js|jsx|cs|rb|php|scala|rs|cpp|c|h))(?::\d+)?", symptom)
    return match.group(1) if match else None


def _build_notify_args(*, case_request: CaseCreateRequest, report: CaseReport) -> dict[str, Any]:
    cause_title = report.root_cause.title if report.root_cause is not None else "pending"
    # Get channel from metadata or use default
    channel = case_request.metadata.get("notify_channel", "webhook")
    return {
        "channel": channel,
        "message": (
            f"[{case_request.service_name}] {case_request.title} | "
            f"root_cause={cause_title} | evidence={len(report.evidence_item_ids)}"
        ),
    }


def _map_result_to_evidence(*, pack: EvidencePack, action: str, content: dict[str, Any]) -> None:
    if action == "incident.normalize":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.OTHER, content=content)
        return
    if action == "log.query_by_trace_id":
        log_result = LogQueryResult.model_validate(content)
        append_log_query_evidence(pack, tool_name=action, result=log_result)
        return
    if action == "log.query_by_template":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.LOG, content=content)
        return
    if action == "trace.get_chain":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.TRACE, content=content)
        return
    if action == "code.search":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.CODE, content=content)
        return
    if action == "code.read":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.CODE, content=content)
        return
    if action == "index.get_status":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.OTHER, content=content)
        return
    if action == "repo.list":
        append_tool_json_evidence(pack, tool_name=action, evidence_type=EvidenceType.CODE, content=content)
        return
    if action.startswith("catalog."):
        append_tool_json_evidence(
            pack,
            tool_name=action,
            evidence_type=EvidenceType.SERVICE_CATALOG,
            content=content,
        )
