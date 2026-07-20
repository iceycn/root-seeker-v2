from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from rootseeker.cron.jobs import CronJobState, JobRunResult
from rootseeker.infra_core.settings import RootSeekerSettings
from rootseeker.storage.backend_resolve import resolve_cron_state_store
from rootseeker.storage.mysql_conn import mysql_config_from_settings

__all__ = [
    "CronStateStore",
    "FileCronStateStore",
    "InMemoryCronStateStore",
    "MysqlCronStateStore",
    "build_cron_state_store",
]


class CronStateStore(ABC):
    @abstractmethod
    def get_state(self, job_id: str) -> CronJobState | None: ...

    @abstractmethod
    def save_state(self, state: CronJobState) -> None: ...

    @abstractmethod
    def append_run(self, result: JobRunResult) -> None: ...

    @abstractmethod
    def list_runs(self, job_id: str | None = None) -> list[JobRunResult]: ...


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


def build_cron_state_store(
    repo_root: Path,
    *,
    settings: RootSeekerSettings | None = None,
    state_path: Path | None = None,
) -> CronStateStore:
    """Build file or MySQL cron state store from settings."""
    from rootseeker.cron.mysql_state_store import MysqlCronStateStore

    cfg = settings or RootSeekerSettings()
    if resolve_cron_state_store(cfg) == "mysql":
        return MysqlCronStateStore(mysql_config_from_settings(cfg))
    path = state_path or Path(cfg.cron_state_path)
    if not path.is_absolute():
        path = repo_root / path
    return FileCronStateStore(path)


def __getattr__(name: str):
    if name == "MysqlCronStateStore":
        from rootseeker.cron.mysql_state_store import MysqlCronStateStore

        return MysqlCronStateStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")