from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime.checkpoint import FlowCheckpointStore
from rootseeker.flow_runtime.flow_executor import FlowExecutionResult, FlowExecutor

__all__ = ["FlowRuntime"]


@dataclass
class FlowRuntime:
    runtime: DevRuntime
    checkpoints: FlowCheckpointStore

    def __init__(self, runtime: DevRuntime, checkpoints: FlowCheckpointStore | None = None) -> None:
        self.runtime = runtime
        self.checkpoints = checkpoints or runtime.flow_checkpoint_store
        self._executor = FlowExecutor(runtime)

    def run_default(
        self,
        case_request: CaseCreateRequest,
        *,
        publish_completion: bool = True,
    ) -> FlowExecutionResult:
        result = self._executor.execute_default(
            case_request,
            publish_completion=publish_completion,
        )
        self.checkpoints.save(
            result.trace.execution_id, _build_checkpoint_payload(result, status=result.status)
        )
        return result

    def list_checkpoints(
        self,
        *,
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        records = self.checkpoints.list_records(case_id=case_id, status=status, limit=limit)
        return [
            {
                "flow_run_id": r.flow_run_id,
                "revision": r.revision,
                "updated_at": r.updated_at.isoformat(),
                "payload": dict(r.payload),
            }
            for r in records
        ]


def _build_checkpoint_payload(
    result: FlowExecutionResult,
    *,
    status: str,
    resumed_from_execution_id: str | None = None,
    resume_status: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "case_id": result.case_id,
        "flow_id": result.trace.flow_id,
        "skill_slug": result.trace.skill_slug,
        "status": status,
        "next_step_index": len(result.trace.steps),
        "steps": [
            {
                "step_id": step.step_id,
                "name": step.name,
                "status": step.status.value,
                "tool_name": step.tool_name,
                "outputs": result.step_outputs.get(step.step_id, {}),
            }
            for step in result.trace.steps
        ],
    }
    if resumed_from_execution_id is not None:
        payload["resumed_from_execution_id"] = resumed_from_execution_id
    if resume_status is not None:
        payload["resume_status"] = resume_status
    return payload
