"""SQLite-backed replay history store compatible with ReplayStore API."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rootseeker.contracts.replay import ReplayCaseSpec, ReplayRunSnapshot
from rootseeker.replay.store import ReplayHistory, ReplayStore

__all__ = ["SqliteReplayHistoryStore"]


class SqliteReplayHistoryStore(ReplayStore):
    """Persist replay fixtures and run snapshots alongside the main SQLite database."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._init_db()
        super().__init__()
        self._hydrate()

    def upsert_case(self, case: ReplayCaseSpec) -> None:
        super().upsert_case(case)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO replay_history_cases (replay_id, data)
                VALUES (?, ?)
                """,
                (case.replay_id, case.model_dump_json()),
            )

    def add_run(self, run: ReplayRunSnapshot) -> None:
        super().add_run(run)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO replay_history_runs (run_id, replay_id, data)
                VALUES (?, ?, ?)
                """,
                (run.run_id, run.replay_id, run.model_dump_json()),
            )

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_history_cases (
                    replay_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_history_runs (
                    run_id TEXT PRIMARY KEY,
                    replay_id TEXT NOT NULL,
                    data TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_replay_history_runs_replay_id "
                "ON replay_history_runs(replay_id)"
            )

    def _hydrate(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            case_rows = conn.execute("SELECT data FROM replay_history_cases").fetchall()
            run_rows = conn.execute(
                "SELECT replay_id, data FROM replay_history_runs ORDER BY rowid"
            ).fetchall()

        for (data,) in case_rows:
            case = ReplayCaseSpec.model_validate_json(data)
            self._cases[case.replay_id] = ReplayHistory(case=case, runs=[])

        for replay_id, data in run_rows:
            run = ReplayRunSnapshot.model_validate_json(data)
            history = self._cases.get(replay_id)
            if history is not None:
                history.runs.append(run)
