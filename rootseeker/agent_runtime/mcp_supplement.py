"""Run optional external MCP tool calls after the deterministic default flow."""

from __future__ import annotations

import json
from typing import Any

from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.evidence import EvidencePack, EvidenceType
from rootseeker.contracts.skill import SkillSpec
from rootseeker.contracts.tool import ToolCallRequest, ToolCallResult
from rootseeker.evidence import append_tool_json_evidence
from rootseeker.mcp_plane import McpGateway
from rootseeker.mcp_plane.registry import ToolRegistry
from rootseeker.mcp_plane.tool_resolution import list_external_tool_specs, skill_allows_external_mcp
from rootseeker.skill_runtime.result_sanitize import sanitize_tool_result_for_persistence

from .llm_tool_planner import OpenAICompatibleToolPlanner
from .tool_call_loop import ToolCallLoop

__all__ = ["run_external_mcp_supplement"]


def run_external_mcp_supplement(
    *,
    case_request: CaseCreateRequest,
    flow_case_id: str,
    evidence_pack: EvidencePack,
    step_outputs: dict[str, dict[str, Any]],
    skill: SkillSpec | None,
    gateway: McpGateway,
    tool_registry: ToolRegistry,
    tool_call_loop: ToolCallLoop | None = None,
    tool_planner: OpenAICompatibleToolPlanner | None = None,
) -> list[ToolCallResult]:
    if not skill_allows_external_mcp(skill):
        return []
    external_tools = list_external_tool_specs(tool_registry)
    if not external_tools:
        return []

    planner = tool_planner or OpenAICompatibleToolPlanner.from_settings()
    if planner is None:
        return []

    enriched_request = _enrich_case_request(case_request, step_outputs=step_outputs)
    history_summary = _flow_history_summary(step_outputs)
    plan_result = planner.plan(
        case_request=enriched_request,
        tools=external_tools,
        history_summary=history_summary,
    )
    if not plan_result.ok or plan_result.plan is None:
        return []

    loop = tool_call_loop or ToolCallLoop(gateway=gateway)
    tool_results: list[ToolCallResult] = []
    for call in plan_result.plan.tool_calls:
        request = ToolCallRequest(
            case_id=flow_case_id,
            step_id=call.step_id,
            skill_name=skill.slug if skill is not None else "default-log-triage",
            tool_name=call.tool_name,
            arguments=dict(call.arguments),
        )
        record = loop.execute_records(
            [request],
            plugin_id="builtin.external_mcp_supplement",
            actor="mcp-supplement",
        )[0]
        tool_results.append(record.result)
        if record.result.ok:
            content = sanitize_tool_result_for_persistence(record.result.content)
            append_tool_json_evidence(
                pack=evidence_pack,
                action=call.tool_name,
                content=content,
                evidence_type=EvidenceType.TOOL_OUTPUT,
                title=f"MCP: {call.tool_name}",
            )
    return tool_results


def _enrich_case_request(
    case_request: CaseCreateRequest,
    *,
    step_outputs: dict[str, dict[str, Any]],
) -> CaseCreateRequest:
    metadata = dict(case_request.metadata or {})
    metadata["flow_step_outputs_preview"] = _compact_step_outputs(step_outputs)
    return CaseCreateRequest(
        title=case_request.title,
        symptom=case_request.symptom,
        service_name=case_request.service_name,
        source=case_request.source,
        metadata=metadata,
    )


def _compact_step_outputs(step_outputs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for step_id, payload in list(step_outputs.items())[:12]:
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > 1200:
            text = text[:1200] + "..."
        preview[step_id] = text
    return preview


def _flow_history_summary(step_outputs: dict[str, dict[str, Any]]) -> str:
    fragments = [f"{step_id} completed" for step_id in list(step_outputs.keys())[:8]]
    if not fragments:
        return ""
    return "prior_flow=" + ",".join(fragments)
