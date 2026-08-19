from __future__ import annotations

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.case import CaseCreateRequest
from rootseeker.contracts.task import TaskKind, TaskStatus
from rootseeker.flow_runtime import FlowRuntime
from rootseeker.governance import DeploymentPolicyOrchestrator
from rootseeker.replay import ReplayRunner, default_replay_suite
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
        try:
            self._execute_task(task)
        except Exception as exc:  # noqa: BLE001 — persist failure before propagating
            task.status = TaskStatus.FAILED
            task.error = {"reason": str(exc), "type": type(exc).__name__}
            self._store.save(task)
            raise

    def _execute_task(self, task) -> None:
        if task.kind == TaskKind.CASE_RUN:
            req = CaseCreateRequest.model_validate(task.payload)
            if self._runtime.resolve_use_agent(bool(task.payload.get("use_agent", False))):
                agent_result = self._runtime.run_agent_from_case_request(req)
                task.result_ref = agent_result.case_id
                task.payload["runner"] = "agent"
                task.payload["attempt_count"] = len(agent_result.attempts)
                task.status = TaskStatus.COMPLETED
                self._store.save(task)
                return
            res = self._flow_runtime.run_default(req)
            task.result_ref = res.case_id
            task.payload["flow_run_id"] = res.trace.execution_id
            task.status = TaskStatus.COMPLETED
            self._store.save(task)
            return
        if task.kind in {TaskKind.CRON, TaskKind.REPLAY}:
            suite_name = str(task.payload.get("suite_name", "cron-default-flow"))
            repeat_each = int(task.payload.get("repeat_each", 1))
            runner = ReplayRunner(self._runtime, self._runtime.replay_store)
            runner.load_cases(default_replay_suite())
            result = runner.run_suite(suite_name=suite_name, repeat_each=max(1, repeat_each))
            task.result_ref = result.report.report_id
            task.payload["report_suite_name"] = result.report.suite_name
            task.payload["report_case_count"] = result.report.case_count
            task.payload["report_gate_passed"] = result.report.gate_passed
            decision = DeploymentPolicyOrchestrator(self._runtime.approval_store).evaluate(
                result.report
            )
            task.payload["report_release_allowed"] = decision.release_allowed
            task.payload["deployment_decision"] = decision.to_payload()
            task.status = TaskStatus.COMPLETED
            self._store.save(task)
            return
        task.status = TaskStatus.FAILED
        task.error = {"reason": f"unsupported kind: {task.kind.value}"}
        self._store.save(task)
