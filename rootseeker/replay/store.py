from __future__ import annotations

from dataclasses import dataclass, field

from rootseeker.contracts.replay import ReplayCaseSpec, ReplayRunSnapshot

__all__ = ["ReplayStore", "ReplayHistory"]


@dataclass
class ReplayHistory:
    case: ReplayCaseSpec
    runs: list[ReplayRunSnapshot] = field(default_factory=list)


class ReplayStore:
    """In-memory replay store: benchmark fixtures + per-case historical runs."""

    def __init__(self) -> None:
        self._cases: dict[str, ReplayHistory] = {}

    def upsert_case(self, case: ReplayCaseSpec) -> None:
        history = self._cases.get(case.replay_id)
        if history is None:
            self._cases[case.replay_id] = ReplayHistory(case=case, runs=[])
            return
        history.case = case

    def add_run(self, run: ReplayRunSnapshot) -> None:
        history = self._cases.get(run.replay_id)
        if history is None:
            raise ValueError(f"Replay case not found: {run.replay_id}")
        history.runs.append(run)

    def list_cases(self) -> list[ReplayCaseSpec]:
        return [h.case for h in self._cases.values()]

    def get_case(self, replay_id: str) -> ReplayCaseSpec | None:
        history = self._cases.get(replay_id)
        return history.case if history else None

    def get_runs(self, replay_id: str) -> list[ReplayRunSnapshot]:
        history = self._cases.get(replay_id)
        return list(history.runs) if history else []
