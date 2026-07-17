from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.flow_runtime.checkpoint import FlowCheckpointStore
from rootseeker.flow_runtime.flow_executor import FlowExecutionResult, FlowExecutor

__all__ = ["FlowRuntime", "resolve_resume_step_index"]


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
        self.checkpoints.save(
            result.trace.execution_id, _build_checkpoint_payload(result, status="completed")
        )
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
        prior_step_outputs: dict[str, dict[str, Any]] = {}
        for step_info in current.get("steps", []):
            step_id = str(step_info.get("step_id", ""))
            outputs = step_info.get("outputs")
            if step_id and isinstance(outputs, dict):
                prior_step_outputs[step_id] = dict(outputs)

        prior_case_id = str(current.get("case_id", ""))
        next_step_index = resolve_resume_step_index(
            current_steps=list(current.get("steps", [])),
            current_next_step_index=int(current.get("next_step_index", 0)),
            flow_step_ids=self._current_flow_step_ids(),
        )

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

    def _current_flow_step_ids(self) -> list[str]:
        skill = self.runtime.skill_registry.get("flows/default-log-triage")
        if skill is None:
            return []
        return [step.step_id for step in skill.steps]


def resolve_resume_step_index(
    *,
    current_steps: list[dict[str, Any]],
    current_next_step_index: int,
    flow_step_ids: list[str],
) -> int:
    """Map a checkpoint resume index onto the current flow by step_id.

    Old checkpoints may store next_step_index against a previous step layout
    (e.g. before find-callers was inserted). Prefer the first unfinished
    step_id in the current flow; fall back to the stored index when mapping
    is impossible.
    """
    if not flow_step_ids:
        return max(0, current_next_step_index)

    completed_ids: set[str] = set()
    for step_info in current_steps:
        step_id = str(step_info.get("step_id", "")).strip()
        status = str(step_info.get("status", "")).strip().lower()
        if step_id and status in {"completed", "skipped", "success"}:
            completed_ids.add(step_id)

    for idx, step_id in enumerate(flow_step_ids):
        if step_id not in completed_ids:
            return idx
    return len(flow_step_ids)


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
