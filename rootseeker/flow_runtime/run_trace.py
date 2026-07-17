from __future__ import annotations

from rootseeker.contracts.case import CaseStep, StepStatus
from rootseeker.contracts.common import new_id
from rootseeker.contracts.execution_trace import ExecutionTrace, StepExecutionRecord

__all__ = ["build_execution_trace"]


def build_execution_trace(
    *,
    case_id: str,
    skill_slug: str,
    flow_id: str,
    step_names: list[str] | None = None,
    case_steps: list[CaseStep] | None = None,
) -> ExecutionTrace:
    if case_steps is None and step_names is None:
        raise ValueError("either step_names or case_steps must be provided")
    if case_steps is not None:
        steps = [
            StepExecutionRecord(
                step_id=step.step_id,
                name=step.name,
                status=step.status,
                capability=step.action,
                tool_name=step.tool_name,
                started_at=None,
                finished_at=None,
                detail={
                    "inputs": dict(step.inputs),
                    "outputs": dict(step.outputs),
                },
            )
            for step in case_steps
        ]
    else:
        steps = [
            StepExecutionRecord(
                step_id=f"step-{idx + 1}",
                name=name,
                status=StepStatus.COMPLETED,
            )
            for idx, name in enumerate(step_names or [])
        ]
    return ExecutionTrace(
        execution_id=new_id("exec-"),
        case_id=case_id,
        skill_slug=skill_slug,
        flow_id=flow_id,
        steps=steps,
    )
