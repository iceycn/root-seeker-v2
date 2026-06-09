from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from rootseeker.cron.jobs import CronJobState, JobRunResult

__all__ = ["CronStateStore", "FileCronStateStore", "InMemoryCronStateStore"]


class CronStateStore(ABC):
    @abstractmethod
    def get_state(self, job_id: str) -> CronJobState | None:
        ...

    @abstractmethod
    def save_state(self, state: CronJobState) -> None:
        ...

    @abstractmethod
    def append_run(self, result: JobRunResult) -> None:
        ...

    @abstractmethod
    def list_runs(self, job_id: str | None = None) -> list[JobRunResult]:
        ...


class InMemoryCronStateStore(CronStateStore):
    def __init__(self) -> None:
        self._states: dict[str, CronJobState] = {}
        self._runs: list[JobRunResult] = []

    def get_state(self, job_id: str) -> CronJobState | None:
        return self._states.get(job_id)

    def save_state(self, state: CronJobState) -> None:
        self._states[state.job_id] = state

    def append_run(self, result: JobRunResult) -> None:
        self._runs.append(result)

    def list_runs(self, job_id: str | None = None) -> list[JobRunResult]:
        if job_id is None:
            return list(self._runs)
        return [run for run in self._runs if run.job_id == job_id]


class FileCronStateStore(InMemoryCronStateStore):
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__()
        self._load()

    def save_state(self, state: CronJobState) -> None:
        super().save_state(state)
        self._flush()

    def append_run(self, result: JobRunResult) -> None:
        super().append_run(result)
        self._flush()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._states = {
            job_id: CronJobState.model_validate(raw)
            for job_id, raw in data.get("states", {}).items()
        }
        self._runs = [JobRunResult.model_validate(raw) for raw in data.get("runs", [])]

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "states": {
                job_id: state.model_dump(mode="json") for job_id, state in self._states.items()
            },
            "runs": [run.model_dump(mode="json") for run in self._runs],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
