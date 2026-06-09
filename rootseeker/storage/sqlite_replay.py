"""SQLite-based replay store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rootseeker.contracts.common import utc_now


@dataclass
class ReplayCaseRecord:
    """Record for a replay case."""

    case_id: str
    suite_name: str
    payload: dict[str, Any]
    created_at: datetime


@dataclass
class ReplayResultRecord:
    """Record for a replay result."""

    result_id: str
    suite_name: str
    case_id: str
    status: str
    metrics: dict[str, Any]
    created_at: datetime


@dataclass
class SqliteReplayStore:
    """SQLite-backed replay store for cases and results."""

    db_path: Path

    def __post_init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_cases (
                    case_id TEXT PRIMARY KEY,
                    suite_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS replay_results (
                    result_id TEXT PRIMARY KEY,
                    suite_name TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metrics TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_cases_suite ON replay_cases(suite_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_replay_results_suite ON replay_results(suite_name)")

    def save_case(self, case_id: str, suite_name: str, payload: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO replay_cases
                (case_id, suite_name, payload, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (case_id, suite_name, json.dumps(payload), utc_now().isoformat()),
            )

    def get_case(self, case_id: str) -> ReplayCaseRecord | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM replay_cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()

        if row is None:
            return None

        return ReplayCaseRecord(
            case_id=row[0],
            suite_name=row[1],
            payload=json.loads(row[2]),
            created_at=datetime.fromisoformat(row[3]),
        )

    def list_cases(self, suite_name: str | None = None) -> list[ReplayCaseRecord]:
        with sqlite3.connect(self.db_path) as conn:
            if suite_name:
                rows = conn.execute(
                    "SELECT * FROM replay_cases WHERE suite_name = ? ORDER BY created_at",
                    (suite_name,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM replay_cases ORDER BY created_at").fetchall()

        return [
            ReplayCaseRecord(
                case_id=row[0],
                suite_name=row[1],
                payload=json.loads(row[2]),
                created_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]

    def save_result(
        self,
        result_id: str,
        suite_name: str,
        case_id: str,
        status: str,
        metrics: dict[str, Any],
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO replay_results
                (result_id, suite_name, case_id, status, metrics, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (result_id, suite_name, case_id, status, json.dumps(metrics), utc_now().isoformat()),
            )

    def list_results(self, suite_name: str | None = None, limit: int = 100) -> list[ReplayResultRecord]:
        with sqlite3.connect(self.db_path) as conn:
            if suite_name:
                rows = conn.execute(
                    "SELECT * FROM replay_results WHERE suite_name = ? ORDER BY created_at DESC LIMIT ?",
                    (suite_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM replay_results ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()

        return [
            ReplayResultRecord(
                result_id=row[0],
                suite_name=row[1],
                case_id=row[2],
                status=row[3],
                metrics=json.loads(row[4]) if row[4] else {},
                created_at=datetime.fromisoformat(row[5]),
            )
            for row in rows
        ]

    def clear_cases(self, suite_name: str | None = None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            if suite_name:
                conn.execute("DELETE FROM replay_cases WHERE suite_name = ?", (suite_name,))
            else:
                conn.execute("DELETE FROM replay_cases")
