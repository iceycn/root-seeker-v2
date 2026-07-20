"""MySQL-based task storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from rootseeker.contracts.task import TaskKind, TaskRecord, TaskStatus
from rootseeker.storage.mysql_conn import MysqlConnectConfig, decode_mysql_json, mysql_connection


@dataclass
class MysqlTaskStore:
    """MySQL-backed task store."""

    config: MysqlConnectConfig

    def __post_init__(self) -> None:
        self._init_db()

    def _connect(self):
        return mysql_connection(self.config)

    def _init_db(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id VARCHAR(255) PRIMARY KEY,
                        kind VARCHAR(64) NOT NULL,
                        case_id VARCHAR(255),
                        flow_id VARCHAR(255),
                        skill_slug VARCHAR(255),
                        status VARCHAR(64) NOT NULL,
                        payload JSON,
                        result_ref TEXT,
                        error JSON,
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_tasks_status (status),
                        INDEX idx_tasks_kind (kind)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def save(self, task: TaskRecord) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO tasks
                    (task_id, kind, case_id, flow_id, skill_slug, status,
                     payload, result_ref, error, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task.task_id,
                        task.kind.value,
                        task.case_id,
                        task.flow_id,
                        task.skill_slug,
                        task.status.value,
                        json.dumps(task.payload),
                        task.result_ref,
                        json.dumps(task.error) if task.error else None,
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                    ),
                )

    def get(self, task_id: str) -> TaskRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_task(row)

    def list_all(self) -> list[TaskRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM tasks ORDER BY created_at DESC")
                rows = cur.fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_by_status(self, status: TaskStatus) -> list[TaskRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM tasks WHERE status = %s ORDER BY created_at DESC",
                    (status.value,),
                )
                rows = cur.fetchall()
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: tuple) -> TaskRecord:
        return TaskRecord(
            task_id=row[0],
            kind=TaskKind(row[1]),
            case_id=row[2],
            flow_id=row[3],
            skill_slug=row[4],
            status=TaskStatus(row[5]),
            payload=decode_mysql_json(row[6], default={}),
            result_ref=row[7],
            error=decode_mysql_json(row[8], default=None),
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )
