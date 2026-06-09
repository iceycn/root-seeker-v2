"""SQLite-based task and checkpoint storage implementations."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rootseeker.contracts.task import TaskKind, TaskRecord, TaskStatus


@dataclass
class SqliteTaskStore:
    """SQLite-backed task store."""

    db_path: Path

    def __post_init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    case_id TEXT,
                    flow_id TEXT,
                    skill_slug TEXT,
                    status TEXT NOT NULL,
                    payload TEXT,
                    result_ref TEXT,
                    error TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_kind ON tasks(kind)")

    def save(self, task: TaskRecord) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tasks
                (task_id, kind, case_id, flow_id, skill_slug, status,
                 payload, result_ref, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_task(row)

    def list_all(self) -> list[TaskRecord]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [self._row_to_task(row) for row in rows]

    def list_by_status(self, status: TaskStatus) -> list[TaskRecord]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC",
                (status.value,),
            ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def _row_to_task(self, row: tuple) -> TaskRecord:
        return TaskRecord(
            task_id=row[0],
            kind=TaskKind(row[1]),
            case_id=row[2],
            flow_id=row[3],
            skill_slug=row[4],
            status=TaskStatus(row[5]),
            payload=json.loads(row[6]) if row[6] else {},
            result_ref=row[7],
            error=json.loads(row[8]) if row[8] else None,
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )
