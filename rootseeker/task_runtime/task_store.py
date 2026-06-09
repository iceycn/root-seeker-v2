from __future__ import annotations

from rootseeker.contracts.task import TaskRecord

__all__ = ["TaskStore"]


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}

    def save(self, task: TaskRecord) -> None:
        self._tasks[task.task_id] = task

    def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    def list_all(self) -> list[TaskRecord]:
        return list(self._tasks.values())
