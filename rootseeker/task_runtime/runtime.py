from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rootseeker.bootstrap import DevRuntime
from rootseeker.contracts.task import TaskKind, TaskRecord, TaskStatus
from rootseeker.infra_core import RootSeekerSettings
from rootseeker.storage.mysql_conn import mysql_config_from_settings
from rootseeker.storage.mysql_task import MysqlTaskStore
from rootseeker.storage.sqlite_task import SqliteTaskStore
from rootseeker.task_runtime.task import create_task_record
from rootseeker.task_runtime.task_executor import TaskExecutor
from rootseeker.task_runtime.task_queue import TaskQueue
from rootseeker.task_runtime.task_store import TaskStore

__all__ = ["TaskRuntime"]


@dataclass
class TaskRuntime:
    runtime: DevRuntime
    store: TaskStore | SqliteTaskStore | MysqlTaskStore
    queue: TaskQueue
    executor: TaskExecutor

    def __init__(
        self,
        runtime: DevRuntime,
        *,
        store: TaskStore | SqliteTaskStore | MysqlTaskStore | None = None,
        queue: TaskQueue | None = None,
    ) -> None:
        self.runtime = runtime
        self.store = store or _build_default_task_store(runtime)
        self.queue = queue or TaskQueue()
        self.executor = TaskExecutor(runtime, self.store)

    def submit(self, *, kind: TaskKind, payload: dict, case_id: str | None = None) -> TaskRecord:
        task = create_task_record(kind=kind, payload=payload, case_id=case_id)
        self.store.save(task)
        self.queue.push(task.task_id)
        return task

    def run_once(self) -> TaskRecord | None:
        task_id = self.queue.pop() or _next_pending_task_id(self.store)
        if task_id is None:
            return None
        self.executor.execute(task_id)
        return self.store.get(task_id)


def _build_default_task_store(runtime: DevRuntime) -> TaskStore | SqliteTaskStore | MysqlTaskStore:
    settings = RootSeekerSettings()
    if settings.storage_backend == "mysql":
        return MysqlTaskStore(mysql_config_from_settings(settings))
    if settings.storage_backend == "sqlite":
        db_path = Path(settings.sqlite_db_path)
        if not db_path.is_absolute():
            db_path = runtime.repo_root / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return SqliteTaskStore(db_path)
    return TaskStore()


def _next_pending_task_id(store: TaskStore | SqliteTaskStore | MysqlTaskStore) -> str | None:
    if hasattr(store, "list_by_status"):
        pending = store.list_by_status(TaskStatus.PENDING)
    else:
        pending = [task for task in store.list_all() if task.status == TaskStatus.PENDING]
    if not pending:
        return None
    pending.sort(key=lambda task: task.created_at)
    return pending[0].task_id
