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
    status: str = "completed"


class FlowExecutor:
    def __init__(self, runtime: DevRuntime) -> None:
        self._runtime = runtime

    def execute_default(
        self,
        case_request: CaseCreateRequest,
        *,
        publish_completion: bool = True,
    ) -> FlowExecutionResult:
        result = self._runtime.run_default_flow_from_case_request(
            case_request,
            publish_completion=publish_completion,
        )
        trace = build_execution_trace(
            case_id=result.case.case_id,
            skill_slug=result.case.selected_skills[0] if result.case.selected_skills else "unknown",
            flow_id="builtin.default_log_triage_flow",
            case_steps=result.case.steps,
        )
        step_outputs = {step.step_id: dict(step.outputs) for step in result.case.steps}
        status = result.case.status.value
        return FlowExecutionResult(
            case_id=result.case.case_id,
            trace=trace,
            step_outputs=step_outputs,
            status=status,
        )
