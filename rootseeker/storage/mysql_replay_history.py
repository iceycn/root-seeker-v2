"""MySQL-backed replay history store compatible with ReplayStore API."""

from __future__ import annotations

from rootseeker.contracts.replay import ReplayCaseSpec, ReplayRunSnapshot
from rootseeker.replay.store import ReplayHistory, ReplayStore
from rootseeker.storage.mysql_conn import MysqlConnectConfig, decode_mysql_json, mysql_connection

__all__ = ["MysqlReplayHistoryStore"]


class MysqlReplayHistoryStore(ReplayStore):
    """Persist replay fixtures and run snapshots in MySQL."""

    def __init__(self, config: MysqlConnectConfig) -> None:
        self._config = config
        self._init_db()
        super().__init__()
        self._hydrate()

    def upsert_case(self, case: ReplayCaseSpec) -> None:
        super().upsert_case(case)
        with mysql_connection(self._config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO replay_history_cases (replay_id, data)
                    VALUES (%s, %s)
                    """,
                    (case.replay_id, case.model_dump_json()),
                )

    def add_run(self, run: ReplayRunSnapshot) -> None:
        super().add_run(run)
        with mysql_connection(self._config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO replay_history_runs (run_id, replay_id, data)
                    VALUES (%s, %s, %s)
                    """,
                    (run.run_id, run.replay_id, run.model_dump_json()),
                )

    def _init_db(self) -> None:
        with mysql_connection(self._config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS replay_history_cases (
                        replay_id VARCHAR(255) PRIMARY KEY,
                        data JSON NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS replay_history_runs (
                        run_id VARCHAR(255) PRIMARY KEY,
                        replay_id VARCHAR(255) NOT NULL,
                        data JSON NOT NULL,
                        INDEX idx_replay_history_runs_replay_id (replay_id)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def _hydrate(self) -> None:
        with mysql_connection(self._config) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM replay_history_cases")
                case_rows = cur.fetchall()
                cur.execute(
                    "SELECT replay_id, data FROM replay_history_runs ORDER BY replay_id"
                )
                run_rows = cur.fetchall()

        for (data,) in case_rows:
            case = ReplayCaseSpec.model_validate(decode_mysql_json(data))
            self._cases[case.replay_id] = ReplayHistory(case=case, runs=[])

        for replay_id, data in run_rows:
            run = ReplayRunSnapshot.model_validate(decode_mysql_json(data))
            history = self._cases.get(replay_id)
            if history is not None:
                history.runs.append(run)
