"""SQLite-based checkpoint storage."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rootseeker.contracts.common import utc_now


@dataclass
class FlowCheckpointRecord:
    """Checkpoint record with metadata."""

    flow_run_id: str
    revision: int
    payload: dict[str, Any]
    updated_at: datetime


@dataclass
class SqliteCheckpointStore:
    """SQLite-backed checkpoint store."""

    db_path: Path

    def __post_init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    flow_run_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_case ON checkpoints(flow_run_id)")

    def save(self, flow_run_id: str, payload: dict[str, Any]) -> None:
        existing = self.get_record(flow_run_id)
        revision = (existing.revision + 1) if existing else 1

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (flow_run_id, revision, payload, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (flow_run_id, revision, json.dumps(payload), utc_now().isoformat()),
            )

    def get(self, flow_run_id: str) -> dict[str, Any] | None:
        record = self.get_record(flow_run_id)
        return None if record is None else dict(record.payload)

    def get_record(self, flow_run_id: str) -> FlowCheckpointRecord | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM checkpoints WHERE flow_run_id = ?",
                (flow_run_id,),
            ).fetchone()

        if row is None:
            return None

        return FlowCheckpointRecord(
            flow_run_id=row[0],
            revision=row[1],
            payload=json.loads(row[2]),
            updated_at=datetime.fromisoformat(row[3]),
        )

    def list_records(
        self,
        *,
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[FlowCheckpointRecord]:
        with sqlite3.connect(self.db_path) as conn:
            # Build query with filters
            sql = "SELECT * FROM checkpoints"
            conditions: list[str] = []
            params: list[Any] = []

            if case_id is not None:
                conditions.append("json_extract(payload, '$.case_id') = ?")
                params.append(case_id)
            if status is not None:
                conditions.append("json_extract(payload, '$.status') = ?")
                params.append(status)

            if conditions:
                sql += " WHERE " + " AND ".join(conditions)

            sql += " ORDER BY updated_at DESC"
            if limit > 0:
                sql += f" LIMIT {limit}"

            rows = conn.execute(sql, params).fetchall()

        return [
            FlowCheckpointRecord(
                flow_run_id=row[0],
                revision=row[1],
                payload=json.loads(row[2]),
                updated_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]
