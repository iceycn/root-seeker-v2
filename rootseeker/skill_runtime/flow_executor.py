from __future__ import annotations

from dataclasses import dataclass, field
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
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.report import CaseReport
from rootseeker.contracts.skill import SkillSpec, SkillStepDefinition
from rootseeker.contracts.tool import ToolCallRequest, ToolCallResult
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.mcp_plane import McpGateway, ToolRegistry
from rootseeker.skill_runtime.evidence_mapper import map_tool_result_to_evidence
from rootseeker.skill_runtime.result_sanitize import sanitize_tool_result_for_persistence
from rootseeker.skill_runtime.llm_step_argument_planner import (
    OpenAICompatibleStepArgumentPlanner,
    StepArgumentPlan,
)
from rootseeker.skill_runtime.rule_step_argument_resolver import RuleStepArgumentResolver
from rootseeker.skill_runtime.step_argument_validation import validate_step_arguments
from rootseeker.skill_system.composer import SkillComposer
from rootseeker.skill_system.content_loader import SkillContentLoader
from rootseeker.skill_system.registry import SkillRegistry, get_default_log_triage_skill

DEFAULT_FLOW_PLUGIN_ID = "builtin.default_log_triage_flow"

__all__ = ["SkillFlowRunResult", "StepArgumentPlanner", "execute_skill_flow"]


@dataclass
class SkillFlowRunResult:
    case: CaseRecord
    evidence_pack: EvidencePack
    report: CaseReport
    tool_results: list[ToolCallResult]
    step_traces: list[dict[str, Any]] = field(default_factory=list)


class StepArgumentPlanner:
    def __init__(
        self,
        *,
        settings: RootSeekerSettings | None = None,
        llm_planner: OpenAICompatibleStepArgumentPlanner | None = None,
        rule_resolver: RuleStepArgumentResolver | None = None,
    ) -> None:
        self.settings = settings or RootSeekerSettings()
        self.llm_planner = llm_planner if llm_planner is not None else OpenAICompatibleStepArgumentPlanner.from_settings(
            self.settings
        )
        self.rule_resolver = rule_resolver or RuleStepArgumentResolver()

    def plan(
        self,
        *,
        case_request: CaseCreateRequest,
        action: str,
        tool_spec,
        skill_context,
        step_outputs: dict[str, dict[str, Any]],
        report: CaseReport | None = None,
    ) -> StepArgumentPlan:
        report_summary = None
        if report is not None:
            report_summary = {
                "case_id": report.case_id,
                "evidence_item_ids": list(report.evidence_item_ids),
                "root_cause_title": report.root_cause.title if report.root_cause else None,
            }

        if self.llm_planner is not None and self.settings.skill_llm_argument_planning_enabled:
            llm_plan = self.llm_planner.plan(
                case_request=case_request,
                action=action,
                tool_spec=tool_spec,
                skill_context=skill_context,
                step_outputs=step_outputs,
                report_summary=report_summary,
            )
            if llm_plan is not None:
                validation_error = validate_step_arguments(
                    arguments=llm_plan.arguments,
                    tool_spec=tool_spec,
                    skip=llm_plan.skip,
                )
                if validation_error is None:
                    return llm_plan

        if not self.settings.skill_llm_argument_fallback_enabled:
            return StepArgumentPlan(arguments={}, skip=True, skip_reason="LLM planning failed and fallback disabled.")

        raw = self.rule_resolver.resolve(
            action,
            case_request,
            step_outputs=step_outputs,
            report=report,
        )
        skip_reason = str(raw.pop("_skip_reason", "") or "")
        if skip_reason:
            return StepArgumentPlan(
                arguments={},
                skip=True,
                skip_reason=skip_reason,
                rationale="rule fallback skip",
                argument_source="rule",
            )
        return StepArgumentPlan(
            arguments=raw,
            rationale="rule fallback",
            argument_source="rule",
        )


def execute_skill_flow(
    *,
    case_request: CaseCreateRequest,
    skill_registry: SkillRegistry,
    tool_registry: ToolRegistry,
    gateway: McpGateway,
    composer: SkillComposer | None = None,
    content_loader: SkillContentLoader | None = None,
    argument_planner: StepArgumentPlanner | None = None,
    flow_skill: SkillSpec | None = None,
    plugin_id: str = DEFAULT_FLOW_PLUGIN_ID,
    start_from_step_index: int = 0,
    prior_step_outputs: dict[str, dict[str, Any]] | None = None,
    prior_case_id: str | None = None,
    settings: RootSeekerSettings | None = None,
) -> SkillFlowRunResult:
    settings = settings or RootSeekerSettings()
    composer = composer or SkillComposer(
        skill_registry,
        settings=settings,
        registered_tool_names=tool_registry.known_tools(),
    )
    content_loader = content_loader or SkillContentLoader(settings=settings)
    argument_planner = argument_planner or StepArgumentPlanner(settings=settings)

    if flow_skill is None:
        plan = composer.compose(case_request)
        flow_skill = skill_registry.get(plan.skill_slug)
        if flow_skill is None:
            flow_skill = get_default_log_triage_skill(skill_registry)
    else:
        plan = None

    skill_slug = flow_skill.slug
    case_id = prior_case_id or new_id("case-")
    case = CaseRecord(
        case_id=case_id,
        title=case_request.title,
        symptom=case_request.symptom,
        service_name=case_request.service_name,
        source=case_request.source,
        status=CaseStatus.RUNNING,
        selected_skills=[skill_slug],
        metadata=dict(case_request.metadata),
    )
    case.steps = [
        CaseStep(
            step_id=step.step_id,
            name=step.name,
            skill_name=skill_slug,
            action=step.action,
            status=StepStatus.PENDING,
            tool_name=step.action,
        )
        for step in flow_skill.steps
    ]

    prior_outputs = dict(prior_step_outputs or {})
    for idx, step in enumerate(case.steps):
        if idx < start_from_step_index:
            step.status = StepStatus.COMPLETED
            if step.step_id in prior_outputs:
                step.outputs = dict(prior_outputs[step.step_id])

    pack = EvidencePack(case_id=case.case_id, summary="default flow evidence")
    tool_results: list[ToolCallResult] = []
    step_traces: list[dict[str, Any]] = []
    step_outputs = dict(prior_outputs)
    deferred_steps: list[tuple[SkillStepDefinition, CaseStep]] = []
    display_skill_slug = skill_slug

    for flow_step, case_step in zip(flow_skill.steps, case.steps, strict=True):
        if case_step.status == StepStatus.COMPLETED:
            if case_step.step_id in prior_outputs:
                tool_skill = _resolve_tool_skill(skill_registry, flow_step)
                prior_content = sanitize_tool_result_for_persistence(prior_outputs[case_step.step_id])
                prior_outputs[case_step.step_id] = prior_content
                case_step.outputs = dict(prior_content)
                map_tool_result_to_evidence(
                    pack=pack,
                    action=case_step.action,
                    content=prior_content,
                    tool_skill=tool_skill,
                )
            continue
        if flow_step.defer_until:
            deferred_steps.append((flow_step, case_step))
            continue
        _run_step(
            flow_skill=flow_skill,
            flow_step=flow_step,
            case_step=case_step,
            case=case,
            case_request=case_request,
            skill_registry=skill_registry,
            tool_registry=tool_registry,
            gateway=gateway,
            content_loader=content_loader,
            argument_planner=argument_planner,
            plugin_id=plugin_id,
            pack=pack,
            step_outputs=step_outputs,
            tool_results=tool_results,
            step_traces=step_traces,
            display_skill_slug=display_skill_slug,
        )
        if case.status == CaseStatus.FAILED:
            break

    report = build_case_report(case_id=case.case_id, title=case.title, pack=pack)

    for flow_step, case_step in deferred_steps:
        if case.status == CaseStatus.FAILED:
            break
        _run_step(
            flow_skill=flow_skill,
            flow_step=flow_step,
            case_step=case_step,
            case=case,
            case_request=case_request,
            skill_registry=skill_registry,
            tool_registry=tool_registry,
            gateway=gateway,
            content_loader=content_loader,
            argument_planner=argument_planner,
            plugin_id=plugin_id,
            pack=pack,
            step_outputs=step_outputs,
            tool_results=tool_results,
            step_traces=step_traces,
            report=report,
            display_skill_slug=display_skill_slug,
        )

    if case.status != CaseStatus.FAILED:
        case.status = CaseStatus.COMPLETED
    case.updated_at = utc_now()
    report = build_case_report(case_id=case.case_id, title=case.title, pack=pack)
    return SkillFlowRunResult(
        case=case,
        evidence_pack=pack,
        report=report,
        tool_results=tool_results,
        step_traces=step_traces,
    )


def _run_step(
    *,
    flow_skill: SkillSpec,
    flow_step: SkillStepDefinition,
    case_step: CaseStep,
    case: CaseRecord,
    case_request: CaseCreateRequest,
    skill_registry: SkillRegistry,
    tool_registry: ToolRegistry,
    gateway: McpGateway,
    content_loader: SkillContentLoader,
    argument_planner: StepArgumentPlanner,
    plugin_id: str,
    pack: EvidencePack,
    step_outputs: dict[str, dict[str, Any]],
    tool_results: list[ToolCallResult],
    step_traces: list[dict[str, Any]],
    display_skill_slug: str,
    report: CaseReport | None = None,
) -> None:
    tool_skill = _resolve_tool_skill(skill_registry, flow_step)
    skill_context = content_loader.load_step_context(
        flow_skill=flow_skill,
        step=flow_step,
        tool_skill=tool_skill,
    )
    tool_spec = tool_registry.get_spec(flow_step.action)
    if tool_spec is None:
        case_step.status = StepStatus.FAILED
        case.status = CaseStatus.FAILED
        return

    case_step.status = StepStatus.RUNNING
    arg_plan = argument_planner.plan(
        case_request=case_request,
        action=flow_step.action,
        tool_spec=tool_spec,
        skill_context=skill_context,
        step_outputs=step_outputs,
        report=report,
    )
    step_traces.append(
        {
            "step_id": flow_step.step_id,
            "action": flow_step.action,
            "tool_skill_slug": tool_skill.slug,
            **arg_plan.to_step_metadata(),
        }
    )
    case_step.inputs = {
        "arguments": dict(arg_plan.arguments),
        **arg_plan.to_step_metadata(),
    }

    if arg_plan.skip:
        result = ToolCallResult(
            ok=True,
            tool_name=flow_step.action,
            content={"skipped": True, "reason": arg_plan.skip_reason or "skipped by planner"},
        )
        tool_results.append(result)
        persisted = sanitize_tool_result_for_persistence(result.content)
        case_step.outputs = dict(persisted)
        step_outputs[flow_step.step_id] = dict(persisted)
        case_step.status = StepStatus.COMPLETED
        map_tool_result_to_evidence(
            pack=pack,
            action=flow_step.action,
            content=persisted,
            tool_skill=tool_skill,
        )
        return

    req = ToolCallRequest(
        case_id=case.case_id,
        step_id=flow_step.step_id,
        skill_name=display_skill_slug,
        tool_name=flow_step.action,
        arguments=dict(arg_plan.arguments),
    )
    result = gateway.invoke(req, plugin_id=plugin_id, actor="skill-flow-executor")
    tool_results.append(result)
    persisted = sanitize_tool_result_for_persistence(result.content)
    case_step.outputs = dict(persisted)
    if result.ok:
        step_outputs[flow_step.step_id] = dict(persisted)
        case_step.status = StepStatus.COMPLETED
        if flow_step.action == "incident.normalize":
            cr = persisted.get("case_request")
            if isinstance(cr, dict):
                inferred = str(cr.get("service_name") or "").strip()
                if inferred:
                    case.service_name = inferred
                    # Keep the in-flight request in sync for notify / later planners.
                    case_request.service_name = inferred
        map_tool_result_to_evidence(
            pack=pack,
            action=flow_step.action,
            content=persisted,
            tool_skill=tool_skill,
        )
    else:
        case_step.status = StepStatus.FAILED
        case.status = CaseStatus.FAILED


def _resolve_tool_skill(skill_registry: SkillRegistry, step: SkillStepDefinition) -> SkillSpec:
    slug = step.tool_skill_slug.strip() if step.tool_skill_slug else ""
    if slug:
        spec = skill_registry.get(slug)
        if spec is not None:
            return spec
    resolved = skill_registry.resolve_tool_skill(step.action)
    if resolved is not None:
        return resolved
    raise ValueError(f"No tool skill for action {step.action!r} (step {step.step_id})")
