from __future__ import annotations

from typing import Any

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.governance import DeploymentPolicyOrchestrator
from rootseeker.replay import ReplayRunner, ReplayStore, default_replay_suite
from rootseeker.storage.sqlite_task import SqliteTaskStore
from rootseeker.task_runtime.task_store import TaskStore

__all__ = ["TaskExecutor"]


class TaskExecutor:
    def __init__(self, runtime: DevRuntime, store: TaskStore | SqliteTaskStore) -> None:
        self._runtime = runtime
        self._store = store
        self._flow_runtime = FlowRuntime(runtime)

    def execute(self, task_id: str) -> None:
        task = self._store.get(task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        task.status = TaskStatus.RUNNING
        self._store.save(task)
        if task.kind == TaskKind.CASE_RUN:
            req = CaseCreateRequest.model_validate(task.payload)
            res = self._flow_runtime.run_default(req)
            task.result_ref = res.case_id
            task.payload["flow_run_id"] = res.trace.execution_id
            task.status = TaskStatus.COMPLETED
            self._store.save(task)
            return
        if task.kind == TaskKind.FLOW_RESUME:
            flow_run_id = str(task.payload.get("flow_run_id", ""))
            if not flow_run_id:
                raise ValueError("flow_resume task requires flow_run_id")
            req_payload = task.payload.get("case_request", {})
            req = CaseCreateRequest.model_validate(req_payload)
            force = bool(task.payload.get("force", False))
            resumed = self._flow_runtime.resume_default(
                flow_run_id=flow_run_id,
                case_request=req,
                force=force,
            )
            if resumed is None:
                task.result_ref = flow_run_id
                task.payload["resume_status"] = "skipped_completed"
            else:
                task.result_ref = resumed.case_id
                checkpoint = self._flow_runtime.checkpoints.get(flow_run_id) or {}
                task.payload["resume_status"] = checkpoint.get("resume_status", "unknown")
            task.status = TaskStatus.COMPLETED
            self._store.save(task)
            return
        if task.kind == TaskKind.FLOW_STEP:
            # Execute a single step from a checkpoint
            flow_run_id = str(task.payload.get("flow_run_id", ""))
            step_index = int(task.payload.get("step_index", 0))
            if not flow_run_id:
                raise ValueError("flow_step task requires flow_run_id")
            record = self._flow_runtime.checkpoints.get_record(flow_run_id)
            if record is None:
                task.status = TaskStatus.FAILED
                task.error = {"reason": f"checkpoint not found: {flow_run_id}"}
                self._store.save(task)
                return
            req_payload = task.payload.get("case_request", {})
            req = CaseCreateRequest.model_validate(req_payload)
            prior_outputs: dict[str, dict[str, Any]] = {}
            for step_info in record.payload.get("steps", []):
                step_id = str(step_info.get("step_id", ""))
                outputs = step_info.get("outputs")
                if step_id and isinstance(outputs, dict):
                    prior_outputs[step_id] = dict(outputs)
            prior_case_id = str(record.payload.get("case_id", ""))
            from rootseeker.flow_runtime.flow_executor import FlowExecutor

            executor = FlowExecutor(self._runtime)
            result = executor.execute_from_checkpoint(
                req,
                start_from_step_index=step_index,
                prior_step_outputs=prior_outputs,
                prior_case_id=prior_case_id,
            )
            task.result_ref = result.case_id
            task.payload["executed_step_index"] = step_index
            task.status = TaskStatus.COMPLETED
            self._store.save(task)
            return
        if task.kind in {TaskKind.CRON, TaskKind.REPLAY}:
            suite_name = str(task.payload.get("suite_name", "cron-default-flow"))
            repeat_each = int(task.payload.get("repeat_each", 1))
            runner = ReplayRunner(self._runtime, ReplayStore())
            runner.load_cases(default_replay_suite())
            result = runner.run_suite(suite_name=suite_name, repeat_each=max(1, repeat_each))
            task.result_ref = result.report.report_id
            task.payload["report_suite_name"] = result.report.suite_name
            task.payload["report_case_count"] = result.report.case_count
            task.payload["report_gate_passed"] = result.report.gate_passed
            decision = DeploymentPolicyOrchestrator(self._runtime.approval_store).evaluate(result.report)
            task.payload["report_release_allowed"] = decision.release_allowed
            task.payload["deployment_decision"] = decision.to_payload()
            task.status = TaskStatus.COMPLETED
            self._store.save(task)
            return
        task.status = TaskStatus.FAILED
        task.error = {"reason": f"unsupported kind: {task.kind.value}"}
        self._store.save(task)
