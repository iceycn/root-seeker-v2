from __future__ import annotations

import inspect
import os
from collections.abc import Iterable
from pathlib import Path
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
from rootseeker.contracts.skill import SkillSpec
from rootseeker.contracts.state_machine import validate_case_transition, validate_step_transition
from rootseeker.contracts.tool import ToolCallRequest
from rootseeker.evidence import append_tool_json_evidence
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.mcp_plane.tool_resolution import resolve_planner_tools
from rootseeker.skill_runtime.result_sanitize import (
    sanitize_tool_result_for_evidence,
    sanitize_tool_result_for_persistence,
)
from rootseeker.skill_system.env_resolver import resolve_skill_env, substitute_non_secret
from rootseeker.skill_system.errors import SkillError
from rootseeker.skill_system.parser import load_skill_body
from rootseeker.skill_system.playbook import PlaybookResolver

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
        self.loaded_helpers: list[SkillSpec] = []

    def run_once(
        self,
        case_request: CaseCreateRequest,
        *,
        prior_attempts: list[AttemptResult] | None = None,
        allow_default_fallback: bool = False,
    ) -> AttemptResult:
        del allow_default_fallback
        history_summary = build_attempt_history_summary(prior_attempts or [])
        prompt_messages = self.prompt_builder.build_messages(
            case_request, history_summary=history_summary
        )
        route = self.model_router.select_route(case_request)
        try:
            playbook = self._resolve_playbook(case_request)
        except SkillError as exc:
            return self._fail_attempt(
                case_request=case_request,
                prompt_messages=prompt_messages,
                route=route,
                error_code=exc.code,
                reason=str(exc),
            )

        manager = self.flow_runtime.runtime.mcp_server_manager
        previous_extra = dict(manager.extra_env)
        previous_provider = manager.extra_env_provider
        try:
            try:
                resolution = self._resolve_playbook_env(playbook)
            except SkillError as exc:
                return self._fail_attempt(
                    case_request=case_request,
                    prompt_messages=prompt_messages,
                    route=route,
                    error_code=exc.code,
                    reason=str(exc),
                    skill_slug=playbook.name,
                )
            manager.set_run_env_overlay(resolution.mcp_extra)
            playbook_text = substitute_non_secret(
                self._load_playbook_body(playbook),
                resolution.substitutions,
            )
            if self.tool_planner is None:
                return self._fail_attempt(
                    case_request=case_request,
                    prompt_messages=prompt_messages,
                    route=route,
                    error_code="SKILL_PLANNER_FAILED",
                    reason="llm planner is not configured",
                    skill_slug=playbook.name,
                )
            return self._run_llm_tool_plan(
                case_request=case_request,
                prompt_messages=prompt_messages,
                route=route,
                history_summary=history_summary,
                playbook=playbook,
                playbook_text=playbook_text,
            )
        finally:
            manager.set_run_env_overlay(None)
            manager.set_extra_env(previous_extra)
            manager.set_extra_env_provider(previous_provider)

    def _run_llm_tool_plan(
        self,
        *,
        case_request: CaseCreateRequest,
        prompt_messages: list[dict[str, str]],
        route,
        history_summary: str | None,
        playbook: SkillSpec,
        playbook_text: str,
    ) -> AttemptResult:
        allowed_tool_names = _allowed_tools_for_run(playbook, self.loaded_helpers)
        planner_tools = [
            spec
            for spec in resolve_planner_tools(
                self.flow_runtime.runtime.tool_registry,
                playbook,
                allow_write_tools=True,
            )
            if spec.name in allowed_tool_names
        ]
        plan_result = _invoke_planner(
            self.tool_planner,
            case_request=case_request,
            tools=planner_tools,
            history_summary=history_summary,
            playbook_text=playbook_text,
            skill_catalog=self._skill_catalog(),
            allowed_tool_names=allowed_tool_names,
        )
        if not plan_result.ok or plan_result.plan is None:
            return self._fail_attempt(
                case_request=case_request,
                prompt_messages=prompt_messages,
                route=route,
                error_code="SKILL_PLANNER_FAILED",
                reason=plan_result.error or "llm planner returned no plan",
                plan_result=plan_result,
                skill_slug=playbook.name,
            )
        disallowed = [
            call.tool_name
            for call in plan_result.plan.tool_calls
            if call.tool_name not in allowed_tool_names
        ]
        if disallowed:
            return self._fail_attempt(
                case_request=case_request,
                prompt_messages=prompt_messages,
                route=route,
                error_code="SKILL_TOOL_NOT_ALLOWED",
                reason=f"tool not allowed: {', '.join(disallowed)}",
                plan_result=plan_result,
                skill_slug=playbook.name,
            )

        case = _build_case_from_plan(case_request, plan_result, skill_slug=playbook.name)
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
                    dep_step_id
                    for dep_step_id in call.depends_on
                    if dep_step_id in blocking_step_ids
                ]
                if not blocked_dependencies:
                    continue
                step = steps_by_step_id[step_id]
                request = requests_by_step_id[step_id]
                _transition_step_status(step, StepStatus.SKIPPED)
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
                if all(
                    dep_step_id in finished_step_ids
                    for dep_step_id in calls_by_step_id[step_id].depends_on
                )
            ]
            if not ready_step_ids:
                if skipped_this_wave:
                    continue
                for step_id in list(pending_step_ids):
                    step = steps_by_step_id[step_id]
                    request = requests_by_step_id[step_id]
                    call = calls_by_step_id[step_id]
                    _transition_step_status(step, StepStatus.SKIPPED)
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

            for step_id in ready_step_ids:
                _transition_step_status(steps_by_step_id[step_id], StepStatus.RUNNING)
            if case.status == CaseStatus.PLANNED:
                _transition_case_status(case, CaseStatus.RUNNING)

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
                _transition_step_status(step, StepStatus.COMPLETED)
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
                _transition_step_status(step, StepStatus.FAILED)
        failed = any(
            step.status in {StepStatus.FAILED, StepStatus.SKIPPED}
            and calls_by_step_id[step.step_id].required
            for step in case.steps
        )
        _transition_case_status(
            case,
            CaseStatus.FAILED if failed else CaseStatus.COMPLETED,
        )
        case.updated_at = utc_now()
        notify_skipped = _notify_skipped(allowed_tool_names, plan_result)
        self.flow_runtime.runtime.case_store.put(case)
        self.flow_runtime.runtime.evidence_store.put_pack(pack)
        report = build_case_report(case_id=case.case_id, title=case.title, pack=pack)
        report_metadata = {
            **report.metadata,
            "agent": {
                "route_mode": route.mode,
                "tool_plan": plan_result.to_payload(),
            },
        }
        if notify_skipped:
            report_metadata["notify_skipped"] = True
        report = report.model_copy(update={"metadata": report_metadata})
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
                "skill_slug": playbook.name,
                "step_count": len(case.steps),
                "tool_plan": plan_result.to_payload(),
                **({"notify_skipped": True} if notify_skipped else {}),
            },
        )

    def _resolve_playbook(self, case_request: CaseCreateRequest) -> SkillSpec:
        resolver = PlaybookResolver(
            self.flow_runtime.runtime.skill_registry,
            overlay=self.flow_runtime.runtime.skill_overlay,
        )
        return resolver.resolve(case_request)

    def _resolve_playbook_env(self, playbook: SkillSpec):
        declared_keys = _env_key_list(playbook.metadata.get("env"))
        optional_keys = _env_key_list(
            playbook.metadata.get("optional_env") or playbook.metadata.get("env_optional")
        )
        return resolve_skill_env(
            declared_keys=declared_keys,
            optional_keys=optional_keys,
            process_env={key: str(value) for key, value in os.environ.items()},
            admin_items=_load_admin_env_items(
                self.flow_runtime.runtime.admin_config_root or self.flow_runtime.runtime.repo_root
            ),
            require=True,
        )

    def _load_playbook_body(self, playbook: SkillSpec) -> str:
        skill_dir = playbook.metadata.get("skill_dir")
        if not skill_dir:
            return ""
        path = Path(str(skill_dir)) / "SKILL.md"
        if not path.is_file():
            return ""
        return load_skill_body(path)

    def _skill_catalog(self) -> list[dict[str, str]]:
        catalog: list[dict[str, str]] = []
        for spec in self.flow_runtime.runtime.skill_registry.list_skills():
            if spec.metadata.get("enabled", True) is False:
                continue
            catalog.append({"name": spec.name, "description": spec.description or ""})
        return catalog

    def _fail_attempt(
        self,
        *,
        case_request: CaseCreateRequest,
        prompt_messages: list[dict[str, str]],
        route,
        error_code: str,
        reason: str,
        plan_result: ToolPlanResult | None = None,
        skill_slug: str | None = None,
    ) -> AttemptResult:
        case_id = new_id("case-")
        self._persist_failed_case(
            case_request=case_request,
            case_id=case_id,
            error_code=error_code,
            reason=reason,
            skill_slug=skill_slug,
        )
        payload = (
            plan_result.to_payload() if plan_result is not None else {"ok": False, "error": reason}
        )
        if "error" not in payload:
            payload["error"] = reason
        return AttemptResult(
            attempt_id=new_id("attempt-"),
            case_id=case_id,
            status="failed",
            prompt_messages=prompt_messages,
            route=route,
            tool_traces=[],
            compacted_context=None,
            flow_run_id=None,
            metadata={
                "skill_slug": skill_slug or "agent/llm-tool-plan",
                "step_count": 0,
                "tool_plan": payload,
                "case_title": case_request.title,
                "error_code": error_code,
            },
        )

    def _persist_failed_case(
        self,
        *,
        case_request: CaseCreateRequest,
        case_id: str,
        error_code: str,
        reason: str,
        skill_slug: str | None,
    ) -> None:
        case = CaseRecord(
            case_id=case_id,
            title=case_request.title,
            symptom=case_request.symptom,
            service_name=case_request.service_name,
            source=case_request.source,
            status=CaseStatus.FAILED,
            selected_skills=[skill_slug] if skill_slug else [],
            metadata={
                **case_request.metadata,
                "error_code": error_code,
                "error": reason,
            },
        )
        pack = EvidencePack(case_id=case_id, summary=reason)
        report = build_case_report(case_id=case_id, title=case_request.title, pack=pack)
        report = report.model_copy(
            update={"metadata": {**report.metadata, "error_code": error_code}}
        )
        runtime = self.flow_runtime.runtime
        runtime.case_store.put(case)
        runtime.evidence_store.put_pack(pack)
        runtime.report_store.put(report)


def _invoke_planner(
    planner,
    *,
    case_request: CaseCreateRequest,
    tools,
    history_summary: str | None,
    playbook_text: str,
    skill_catalog: list[dict[str, str]],
    allowed_tool_names: set[str],
) -> ToolPlanResult:
    kwargs: dict[str, Any] = {
        "case_request": case_request,
        "tools": tools,
        "history_summary": history_summary,
        "playbook_text": playbook_text,
        "skill_catalog": skill_catalog,
        "allowed_tool_names": allowed_tool_names,
    }
    try:
        parameters = inspect.signature(planner.plan).parameters
    except (TypeError, ValueError):
        return planner.plan(
            case_request=case_request,
            tools=tools,
            history_summary=history_summary,
        )
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()):
        return planner.plan(**kwargs)
    filtered = {key: value for key, value in kwargs.items() if key in parameters}
    return planner.plan(**filtered)


def _allowed_tools_for_run(
    playbook: SkillSpec,
    loaded_helpers: Iterable[SkillSpec] | None = None,
) -> set[str]:
    names = {str(name).strip() for name in playbook.bound_tools if str(name).strip()}
    for helper in loaded_helpers or []:
        names.update(str(name).strip() for name in helper.bound_tools if str(name).strip())
    return names


def _notify_skipped(allowed_tool_names: set[str], plan_result: ToolPlanResult) -> bool:
    if "notify.send" not in allowed_tool_names or plan_result.plan is None:
        return False
    called = {call.tool_name for call in plan_result.plan.tool_calls}
    return "notify.send" not in called


def _env_key_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part for part in value.split() if part]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _load_admin_env_items(repo_root: Path) -> list[dict[str, Any]]:
    try:
        from apps.admin.config_store import build_admin_config_store

        store = build_admin_config_store(repo_root)
        return store.list_env_vars()
    except Exception:
        return []


def _build_case_from_plan(
    case_request: CaseCreateRequest,
    plan_result: ToolPlanResult,
    *,
    skill_slug: str,
) -> CaseRecord:
    assert plan_result.plan is not None
    case_id = new_id("case-")
    steps = [
        CaseStep(
            step_id=call.step_id,
            name=f"LLM planned {call.tool_name}",
            skill_name=skill_slug,
            action=call.tool_name,
            status=StepStatus.PENDING,
            tool_name=call.tool_name,
            inputs=dict(call.arguments),
        )
        for call in plan_result.plan.tool_calls
    ]
    case = CaseRecord(
        case_id=case_id,
        title=case_request.title,
        symptom=case_request.symptom,
        service_name=case_request.service_name,
        source=case_request.source,
        status=CaseStatus.PENDING,
        selected_skills=[skill_slug],
        steps=steps,
        metadata={
            **case_request.metadata,
            "agent_route": "llm_tool_plan",
            "llm_tool_plan": plan_result.to_payload(),
            "llm_tool_plan_calls": [call.to_payload() for call in plan_result.plan.tool_calls],
        },
    )
    _transition_case_status(case, CaseStatus.PLANNED)
    return case


def _transition_case_status(case: CaseRecord, new: CaseStatus) -> None:
    validate_case_transition(case.status, new)
    case.status = new


def _transition_step_status(case_step: CaseStep, new: StepStatus) -> None:
    validate_step_transition(case_step.status, new)
    case_step.status = new


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
