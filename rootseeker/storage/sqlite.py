"""SQLite-based persistent storage implementations."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rootseeker.contracts.case import CaseRecord
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.report import CaseReport


@dataclass
class SqliteCaseStore:
    """SQLite-backed case store."""

    db_path: Path

    def __post_init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    symptom TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    selected_skills TEXT,
                    steps TEXT,
                    metadata TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

    def put(self, case: CaseRecord) -> None:
        """Store a case record."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cases
                (case_id, title, symptom, service_name, source, status,
                 selected_skills, steps, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case.case_id,
                    case.title,
                    case.symptom,
                    case.service_name,
                    case.source,
                    case.status.value,
                    json.dumps(case.selected_skills),
                    json.dumps([s.model_dump(mode="json") for s in case.steps]),
                    json.dumps(case.metadata),
                    case.created_at.isoformat(),
                    case.updated_at.isoformat(),
                ),
            )

    def get(self, case_id: str) -> CaseRecord | None:
        """Get a case by ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM cases WHERE case_id = ?",
                (case_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_case(row)

    def list_all(self) -> list[CaseRecord]:
        """List all stored cases."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
        return [self._row_to_case(row) for row in rows]

    def _row_to_case(self, row: tuple) -> CaseRecord:
        """Convert database row to CaseRecord."""
        from rootseeker.contracts.case import CaseStatus, CaseStep

        return CaseRecord(
            case_id=row[0],
            title=row[1],
            symptom=row[2],
            service_name=row[3],
            source=row[4],
            status=CaseStatus(row[5]),
            selected_skills=json.loads(row[6]) if row[6] else [],
            steps=[CaseStep.model_validate(s) for s in json.loads(row[7])] if row[7] else [],
            metadata=json.loads(row[8]) if row[8] else {},
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )


@dataclass
class SqliteEvidenceStore:
    """SQLite-backed evidence store."""

    db_path: Path

    def __post_init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence_packs (
                    case_id TEXT PRIMARY KEY,
                    summary TEXT,
                    items TEXT,
                    created_at TEXT
                )
            """)

    def put_pack(self, pack: EvidencePack) -> None:
        """Store an evidence pack."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence_packs
                (case_id, summary, items, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    pack.case_id,
                    pack.summary,
                    json.dumps([i.model_dump(mode="json") for i in pack.items]),
                    datetime.now().isoformat(),
                ),
            )

    def get_pack(self, case_id: str) -> EvidencePack | None:
        """Get evidence pack by case ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM evidence_packs WHERE case_id = ?",
                (case_id,),
            ).fetchone()

        if row is None:
            return None

        from rootseeker.contracts.evidence import EvidenceItem

        items = [EvidenceItem.model_validate(i) for i in json.loads(row[2])]
        return EvidencePack(case_id=row[0], summary=row[1] or "", items=items)


@dataclass
class SqliteReportStore:
    """SQLite-backed report store."""

    db_path: Path

    def __post_init__(self) -> None:
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    case_id TEXT PRIMARY KEY,
                    title TEXT,
                    summary TEXT,
                    root_cause TEXT,
                    evidence_item_ids TEXT,
                    metadata TEXT,
                    generated_at TEXT
                )
            """)

    def put(self, report: CaseReport) -> None:
        """Store a report."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports
                (case_id, title, summary, root_cause, evidence_item_ids, metadata, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.case_id,
                    report.title,
                    report.summary,
                    json.dumps(report.root_cause.model_dump(mode="json"))
                    if report.root_cause
                    else None,
                    json.dumps(report.evidence_item_ids),
                    json.dumps(report.metadata),
                    report.generated_at.isoformat(),
                ),
            )

    def get(self, case_id: str) -> CaseReport | None:
        """Get report by case ID."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE case_id = ?",
                (case_id,),
            ).fetchone()

        if row is None:
            return None

        from rootseeker.contracts.report import RootCauseConclusion

        root_cause = None
        if row[3]:
            root_cause = RootCauseConclusion.model_validate(json.loads(row[3]))

        return CaseReport(
            case_id=row[0],
            title=row[1],
            summary=row[2] or "",
            root_cause=root_cause,
            evidence_item_ids=json.loads(row[4]) if row[4] else [],
            metadata=json.loads(row[5]) if row[5] else {},
            generated_at=datetime.fromisoformat(row[6]),
        )
