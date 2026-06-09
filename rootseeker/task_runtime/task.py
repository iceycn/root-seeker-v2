from __future__ import annotations

from rootseeker.contracts.common import new_id
from rootseeker.contracts.task import TaskKind, TaskRecord

__all__ = ["create_task_record"]


def create_task_record(*, kind: TaskKind, payload: dict, case_id: str | None = None) -> TaskRecord:
    return TaskRecord(
        task_id=new_id("task-"),
        kind=kind,
        case_id=case_id,
        payload=payload,
    )
