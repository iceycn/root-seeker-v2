from __future__ import annotations

from collections import deque

__all__ = ["TaskQueue"]


class TaskQueue:
    def __init__(self) -> None:
        self._q: deque[str] = deque()

    def push(self, task_id: str) -> None:
        self._q.append(task_id)

    def pop(self) -> str | None:
        return self._q.popleft() if self._q else None

    def __len__(self) -> int:
        return len(self._q)
