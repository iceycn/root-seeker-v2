from __future__ import annotations

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
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.evidence import append_tool_json_evidence
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.skill_runtime.result_sanitize import (
    sanitize_tool_result_for_evidence,
    sanitize_tool_result_for_persistence,
)

from .context_compactor import ContextCompactor
from .history_builder import build_attempt_history_summary
from .llm_tool_planner import LlmToolPlanner, OpenAICompatibleToolPlanner
from .model_router import ModelRouter
from .prompt_builder import PromptBuilder
from .result import AttemptResult, ToolExecutionTrace
from .tool_call_loop import ToolCallLoop
from .tool_plan import ToolPlanResult

__all__ = ["AttemptRunner"]


class AttemptRunner:
    def __init__(
        self,
        flow_runtime: FlowRuntime,
        *,
        prompt_builder: PromptBuilder | None = None,
        model_router: ModelRouter | None = None,
        tool_call_loop: ToolCallLoop | None = None,
        context_compactor: ContextCompactor | None = None,
        tool_planner: LlmToolPlanner | None = None,
    ) -> None:
        self.flow_runtime = flow_runtime
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.model_router = model_router or ModelRouter()
        settings = RootSeekerSettings()
        self.tool_call_loop = tool_call_loop or ToolCallLoop(
            gateway=flow_runtime.runtime.gateway,
            max_concurrency=max(1, settings.agent_tool_call_max_concurrency),
        )
        self.context_compactor = context_compactor or ContextCompactor()
        self.tool_planner = tool_planner or OpenAICompatibleToolPlanner.from_settings()

    def run_once(
        self,
        case_request: CaseCreateRequest,
        *,
        prior_attempts: list[AttemptResult] | None = None,
        allow_default_fallback: bool = True,
    ) -> AttemptResult:
        history_summary = build_attempt_history_summary(prior_attempts or [])
        prompt_messages = self.prompt_builder.build_messages(case_request, history_summary=history_summary)
        route = self.model_router.select_route(case_request)
        if route.mode == "llm_tool_plan" and self.tool_planner is not None:
            planned_attempt = self._run_llm_tool_plan(
                case_request=case_request,
                prompt_messages=prompt_messages,
                route=route,
                history_summary=history_summary,
                return_failed_plan=not allow_default_fallback,
            )
            if planned_attempt is not None:
                return planned_attempt
            if not allow_default_fallback:
                return _build_failed_planner_attempt(
                    case_request=case_request,
                    prompt_messages=prompt_messages,
                    route=route,
                    reason="llm planner did not produce executable tool calls",
                )

        flow_result = self.flow_runtime.run_default(case_request)
        tool_traces = self.tool_call_loop.from_flow_result(flow_result)
        compacted_context = self.context_compactor.compact(
            prompt_messages=prompt_messages,
            tool_traces=tool_traces,
        )
        status = _status_from_flow_result(flow_result)
        return AttemptResult(
            attempt_id=new_id("attempt-"),
            case_id=flow_result.case_id,
            status=status,
            prompt_messages=prompt_messages,
            route=route,
            tool_traces=tool_traces,
            compacted_context=compacted_context,
            flow_run_id=flow_result.trace.execution_id,
            metadata={
                "flow_id": flow_result.trace.flow_id,
                "skill_slug": flow_result.trace.skill_slug,
                "step_count": len(flow_result.trace.steps),
                "fallback": route.mode == "llm_tool_plan",
            },
        )

    def _run_llm_tool_plan(
        self,
        *,
        case_request: CaseCreateRequest,
        prompt_messages: list[dict[str, str]],
        route,
        history_summary: str | None,
        return_failed_plan: bool,
    ) -> AttemptResult | None:
        plan_result = self.tool_planner.plan(
            case_request=case_request,
            tools=self.flow_runtime.runtime.tool_registry.list_specs(),
            history_summary=history_summary,
        )
        if not plan_result.ok or plan_result.plan is None:
            if not return_failed_plan:
                return None
            return _build_failed_planner_attempt(
                case_request=case_request,
                prompt_messages=prompt_messages,
                route=route,
                reason=plan_result.error or "llm planner returned no plan",
                plan_result=plan_result,
            )

        case = _build_case_from_plan(case_request, plan_result)
        requests = [
            ToolCallRequest(
                case_id=case.case_id,
                step_id=step.step_id,
                skill_name=step.skill_name,
                tool_name=step.tool_name or step.action,
                arguments=dict(step.inputs),
            )
            for step in case.steps
        ]
        calls_by_step_id = {call.step_id: call for call in plan_result.plan.tool_calls}
        steps_by_step_id = {step.step_id: step for step in case.steps}
        requests_by_step_id = {request.step_id: request for request in requests}
        records_by_step_id = {}
        tool_traces: list[ToolExecutionTrace] = []
        blocking_step_ids: set[str] = set()
        finished_step_ids: set[str] = set()
        pending_step_ids = [step.step_id for step in case.steps]
        while pending_step_ids:
            skipped_this_wave = False
            for step_id in list(pending_step_ids):
                call = calls_by_step_id[step_id]
                blocked_dependencies = [
                    dep_step_id for dep_step_id in call.depends_on if dep_step_id in blocking_step_ids
                ]
                if not blocked_dependencies:
                    continue
                step = steps_by_step_id[step_id]
                request = requests_by_step_id[step_id]
                step.status = StepStatus.SKIPPED
                trace = ToolExecutionTrace(
                    step_id=step.step_id,
                    tool_name=request.tool_name,
                    ok=False,
                    error_code="DEPENDENCY_FAILED",
                    error_message=(
                        "Skipped because dependency steps failed or were skipped: "
                        f"{', '.join(blocked_dependencies)}"
                    ),
                    plan_metadata=call.to_execution_metadata(),
                )
                tool_traces.append(trace)
                finished_step_ids.add(step_id)
                pending_step_ids.remove(step_id)
                if call.required:
                    blocking_step_ids.add(step_id)
                skipped_this_wave = True

            ready_step_ids = [
                step_id
                for step_id in pending_step_ids
                if all(dep_step_id in finished_step_ids for dep_step_id in calls_by_step_id[step_id].depends_on)
            ]
            if not ready_step_ids:
                if skipped_this_wave:
                    continue
                for step_id in list(pending_step_ids):
                    step = steps_by_step_id[step_id]
                    request = requests_by_step_id[step_id]
                    call = calls_by_step_id[step_id]
                    step.status = StepStatus.SKIPPED
                    trace = ToolExecutionTrace(
                        step_id=step_id,
                        tool_name=request.tool_name,
                        ok=False,
                        error_code="DEPENDENCY_CYCLE",
                        error_message="Skipped because tool plan dependencies could not be resolved.",
                        plan_metadata=call.to_execution_metadata(),
                    )
                    tool_traces.append(trace)
                    finished_step_ids.add(step_id)
                    pending_step_ids.remove(step_id)
                    if call.required:
                        blocking_step_ids.add(step_id)
                continue

            records = self.tool_call_loop.execute_records(
                [requests_by_step_id[step_id] for step_id in ready_step_ids],
                actor="agent-runtime",
                plan_metadata_by_step_id={
                    step_id: calls_by_step_id[step_id].to_execution_metadata()
                    for step_id in ready_step_ids
                },
            )
            for record in records:
                step_id = record.request.step_id
                call = calls_by_step_id[step_id]
                records_by_step_id[step_id] = record
                tool_traces.append(record.trace)
                finished_step_ids.add(step_id)
                pending_step_ids.remove(step_id)
                if not record.result.ok and call.required:
                    blocking_step_ids.add(step_id)

        pack = EvidencePack(case_id=case.case_id, summary="llm tool plan evidence")
        for step in case.steps:
            record = records_by_step_id.get(step.step_id)
            if record is None:
                continue
            step.outputs = sanitize_tool_result_for_persistence(record.result.content)
            if record.result.ok:
                step.status = StepStatus.COMPLETED
                append_tool_json_evidence(
                    pack,
                    tool_name=record.result.tool_name,
                    evidence_type=_evidence_type_for_tool(record.result.tool_name),
                    content=sanitize_tool_result_for_evidence(
                        record.result.tool_name,
                        record.result.content,
                    ),
                )
            else:
                step.status = StepStatus.FAILED
        case.status = (
            CaseStatus.FAILED
            if any(
                step.status in {StepStatus.FAILED, StepStatus.SKIPPED}
                and calls_by_step_id[step.step_id].required
                for step in case.steps
            )
            else CaseStatus.COMPLETED
        )
        case.updated_at = utc_now()
        self.flow_runtime.runtime.case_store.put(case)
        self.flow_runtime.runtime.evidence_store.put_pack(pack)
        report = build_case_report(case_id=case.case_id, title=case.title, pack=pack)
        report = report.model_copy(
            update={
                "metadata": {
                    **report.metadata,
                    "agent": {
                        "route_mode": route.mode,
                        "tool_plan": plan_result.to_payload(),
                    },
                }
            }
        )
        self.flow_runtime.runtime.report_store.put(report)

        compacted_context = self.context_compactor.compact(
            prompt_messages=prompt_messages,
            tool_traces=tool_traces,
        )
        return AttemptResult(
            attempt_id=new_id("attempt-"),
            case_id=case.case_id,
            status="failed" if case.status == CaseStatus.FAILED else "completed",
            prompt_messages=prompt_messages,
            route=route,
            tool_traces=tool_traces,
            compacted_context=compacted_context,
            flow_run_id=None,
            metadata={
                "skill_slug": "agent/llm-tool-plan",
                "step_count": len(case.steps),
                "tool_plan": plan_result.to_payload(),
            },
        )


def _status_from_flow_result(flow_result) -> str:
    if any(step.status == StepStatus.FAILED for step in flow_result.trace.steps):
        return "failed"
    return "completed"


def _build_failed_planner_attempt(
    *,
    case_request: CaseCreateRequest,
    prompt_messages: list[dict[str, str]],
    route,
    reason: str,
    plan_result: ToolPlanResult | None = None,
) -> AttemptResult:
    payload = plan_result.to_payload() if plan_result is not None else {"ok": False, "error": reason}
    if "error" not in payload:
        payload["error"] = reason
    return AttemptResult(
        attempt_id=new_id("attempt-"),
        case_id=new_id("case-"),
        status="failed",
        prompt_messages=prompt_messages,
        route=route,
        tool_traces=[],
        compacted_context=None,
        flow_run_id=None,
        metadata={
            "skill_slug": "agent/llm-tool-plan",
            "step_count": 0,
            "tool_plan": payload,
            "case_title": case_request.title,
        },
    )


def _build_case_from_plan(case_request: CaseCreateRequest, plan_result: ToolPlanResult) -> CaseRecord:
    assert plan_result.plan is not None
    case_id = new_id("case-")
    skill_slug = "agent/llm-tool-plan"
    steps = [
        CaseStep(
            step_id=call.step_id,
            name=f"LLM planned {call.tool_name}",
            skill_name=skill_slug,
            action=call.tool_name,
            status=StepStatus.RUNNING,
            tool_name=call.tool_name,
            inputs=dict(call.arguments),
        )
        for call in plan_result.plan.tool_calls
    ]
    return CaseRecord(
        case_id=case_id,
        title=case_request.title,
        symptom=case_request.symptom,
        service_name=case_request.service_name,
        source=case_request.source,
        status=CaseStatus.RUNNING,
        selected_skills=[skill_slug],
        steps=steps,
        metadata={
            **case_request.metadata,
            "agent_route": "llm_tool_plan",
            "llm_tool_plan": plan_result.to_payload(),
            "llm_tool_plan_calls": [call.to_payload() for call in plan_result.plan.tool_calls],
        },
    )


def _evidence_type_for_tool(tool_name: str) -> EvidenceType:
    if tool_name.startswith("log."):
        return EvidenceType.LOG
    if tool_name.startswith("trace."):
        return EvidenceType.TRACE
    if tool_name.startswith("code."):
        return EvidenceType.CODE
    if tool_name.startswith("catalog."):
        return EvidenceType.SERVICE_CATALOG
    return EvidenceType.OTHER
