from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.execution_trace import ExecutionTrace
from rootseeker.flow_runtime.run_trace import build_execution_trace

__all__ = ["FlowExecutionResult", "FlowExecutor"]


@dataclass
class FlowExecutionResult:
    case_id: str
    trace: ExecutionTrace
    step_outputs: dict[str, dict[str, Any]]


class FlowExecutor:
    def __init__(self, runtime: DevRuntime) -> None:
        self._runtime = runtime

    def execute_default(self, case_request: CaseCreateRequest) -> FlowExecutionResult:
        result = self._runtime.run_default_flow_from_case_request(case_request)
        trace = build_execution_trace(
            case_id=result.case.case_id,
            skill_slug=result.case.selected_skills[0] if result.case.selected_skills else "unknown",
            flow_id="builtin.default_log_triage_flow",
            case_steps=result.case.steps,
        )
        step_outputs = {step.step_id: dict(step.outputs) for step in result.case.steps}
        return FlowExecutionResult(
            case_id=result.case.case_id, trace=trace, step_outputs=step_outputs
        )

    def execute_from_checkpoint(
        self,
        case_request: CaseCreateRequest,
        *,
        start_from_step_index: int,
        prior_step_outputs: dict[str, dict[str, Any]],
        prior_case_id: str,
    ) -> FlowExecutionResult:
        """Resume flow execution from a specific step index."""
        result = self._runtime.run_default_flow_from_case_request(
            case_request,
            start_from_step_index=start_from_step_index,
            prior_step_outputs=prior_step_outputs,
            prior_case_id=prior_case_id,
        )
        trace = build_execution_trace(
            case_id=result.case.case_id,
            skill_slug=result.case.selected_skills[0] if result.case.selected_skills else "unknown",
            flow_id="builtin.default_log_triage_flow",
            case_steps=result.case.steps,
        )
        step_outputs = {step.step_id: dict(step.outputs) for step in result.case.steps}
        return FlowExecutionResult(
            case_id=result.case.case_id, trace=trace, step_outputs=step_outputs
        )
