"""MySQL-based checkpoint storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from rootseeker.contracts.common import utc_now
from rootseeker.storage.mysql_conn import MysqlConnectConfig, decode_mysql_json, mysql_connection
from rootseeker.storage.sqlite_checkpoint import FlowCheckpointRecord


@dataclass
class MysqlCheckpointStore:
    """MySQL-backed checkpoint store."""

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
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        flow_run_id VARCHAR(255) PRIMARY KEY,
                        revision INT NOT NULL,
                        payload JSON NOT NULL,
                        updated_at VARCHAR(64) NOT NULL,
                        INDEX idx_checkpoints_updated (updated_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def save(self, flow_run_id: str, payload: dict[str, Any]) -> None:
        # Atomic upsert: new rows start at revision=1; updates bump revision in-place.
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO checkpoints (flow_run_id, revision, payload, updated_at)
                    VALUES (%s, 1, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        revision = revision + 1,
                        payload = VALUES(payload),
                        updated_at = VALUES(updated_at)
                    """,
                    (flow_run_id, json.dumps(payload), utc_now().isoformat()),
                )

    def get(self, flow_run_id: str) -> dict[str, Any] | None:
        record = self.get_record(flow_run_id)
        return None if record is None else dict(record.payload)

    def get_record(self, flow_run_id: str) -> FlowCheckpointRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT flow_run_id, revision, payload, updated_at FROM checkpoints WHERE flow_run_id = %s",
                    (flow_run_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return FlowCheckpointRecord(
            flow_run_id=row[0],
            revision=int(row[1]),
            payload=dict(decode_mysql_json(row[2], default={})),
            updated_at=datetime.fromisoformat(row[3]),
        )

    def list_records(
        self,
        *,
        case_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[FlowCheckpointRecord]:
        sql = "SELECT flow_run_id, revision, payload, updated_at FROM checkpoints"
        conditions: list[str] = []
        params: list[Any] = []
        if case_id is not None:
            conditions.append("JSON_UNQUOTE(JSON_EXTRACT(payload, '$.case_id')) = %s")
            params.append(case_id)
        if status is not None:
            conditions.append("JSON_UNQUOTE(JSON_EXTRACT(payload, '$.status')) = %s")
            params.append(status)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY updated_at DESC"
        if limit > 0:
            sql += f" LIMIT {int(limit)}"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
        return [
            FlowCheckpointRecord(
                flow_run_id=row[0],
                revision=int(row[1]),
                payload=dict(decode_mysql_json(row[2], default={})),
                updated_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]

    def count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM checkpoints")
                row = cur.fetchone()
        return int(row[0] if row else 0)
