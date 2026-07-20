"""MySQL-backed cron state store."""

from __future__ import annotations

import json
from typing import Any

from rootseeker.cron.jobs import CronJobState, JobRunResult
from rootseeker.cron.state_store import CronStateStore
from rootseeker.storage.mysql_conn import MysqlConnectConfig, decode_mysql_json, mysql_connection

__all__ = ["MysqlCronStateStore"]


class MysqlCronStateStore(CronStateStore):
    def __init__(self, config: MysqlConnectConfig) -> None:
        self.config = config
        self._init_db()

    def _connect(self):
        return mysql_connection(self.config)

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cron_job_states (
                        job_id VARCHAR(255) PRIMARY KEY,
                        payload JSON NOT NULL,
                        updated_at VARCHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS cron_job_runs (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        job_id VARCHAR(255) NOT NULL,
                        payload JSON NOT NULL,
                        finished_at VARCHAR(64) NOT NULL,
                        INDEX idx_cron_runs_job (job_id),
                        INDEX idx_cron_runs_finished (finished_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def get_state(self, job_id: str) -> CronJobState | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT payload FROM cron_job_states WHERE job_id = %s",
                    (job_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return CronJobState.model_validate(_as_dict(row[0]))

    def save_state(self, state: CronJobState) -> None:
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
        updated_at = state.updated_at.isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO cron_job_states (job_id, payload, updated_at)
                    VALUES (%s, %s, %s)
                    """,
                    (state.job_id, payload, updated_at),
                )

    def append_run(self, result: JobRunResult) -> None:
        payload = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        finished_at = result.finished_at.isoformat()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cron_job_runs (job_id, payload, finished_at)
                    VALUES (%s, %s, %s)
                    """,
                    (result.job_id, payload, finished_at),
                )

    def list_runs(self, job_id: str | None = None) -> list[JobRunResult]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if job_id is None:
                    cur.execute(
                        "SELECT payload FROM cron_job_runs ORDER BY id ASC"
                    )
                else:
                    cur.execute(
                        "SELECT payload FROM cron_job_runs WHERE job_id = %s ORDER BY id ASC",
                        (job_id,),
                    )
                rows = cur.fetchall()
        return [JobRunResult.model_validate(_as_dict(row[0])) for row in rows]


def _as_dict(raw: Any) -> dict[str, Any]:
    result = decode_mysql_json(raw, default=None)
    if not isinstance(result, dict):
        raise TypeError(f"unexpected JSON payload type: {type(raw)!r}")
    return result
