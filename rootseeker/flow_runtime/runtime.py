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

    def run_default(self, case_request: CaseCreateRequest) -> FlowExecutionResult:
        result = self._executor.execute_default(case_request)
        self.checkpoints.save(result.trace.execution_id, _build_checkpoint_payload(result, status="completed"))
        return result

    def resume_default(
        self,
        *,
        flow_run_id: str,
        case_request: CaseCreateRequest,
        force: bool = False,
    ) -> FlowExecutionResult | None:
        record = self.checkpoints.get_record(flow_run_id)
        if record is None:
            raise ValueError(f"checkpoint not found: {flow_run_id}")

        current = dict(record.payload)
        current_status = str(current.get("status", "unknown"))
        if current_status == "completed" and not force:
            current["resume_status"] = "skipped_completed"
            self.checkpoints.save(flow_run_id, current)
            return None

        # Extract checkpoint state for step resume
        next_step_index = int(current.get("next_step_index", 0))
        prior_step_outputs: dict[str, dict[str, Any]] = {}
        for step_info in current.get("steps", []):
            step_id = str(step_info.get("step_id", ""))
            outputs = step_info.get("outputs")
            if step_id and isinstance(outputs, dict):
                prior_step_outputs[step_id] = dict(outputs)

        prior_case_id = str(current.get("case_id", ""))

        # If we have prior state, resume from checkpoint; otherwise full replay
        if next_step_index > 0 and prior_step_outputs and prior_case_id:
            result = self._executor.execute_from_checkpoint(
                case_request,
                start_from_step_index=next_step_index,
                prior_step_outputs=prior_step_outputs,
                prior_case_id=prior_case_id,
            )
            resume_status = "resumed_from_step"
        else:
            result = self._executor.execute_default(case_request)
            resume_status = "replayed"

        payload = _build_checkpoint_payload(
            result,
            status="completed",
            resumed_from_execution_id=flow_run_id,
            resume_status=resume_status,
        )
        self.checkpoints.save(flow_run_id, payload)
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
