"""MySQL-based persistent storage for cases, evidence, and reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from rootseeker.contracts.case import CaseRecord
from rootseeker.contracts.common import utc_now
from rootseeker.contracts.evidence import EvidencePack
from rootseeker.contracts.report import CaseReport
from rootseeker.storage.mysql_conn import MysqlConnectConfig, decode_mysql_json, mysql_connection


@dataclass
class MysqlCaseStore:
    """MySQL-backed case store."""

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
                    CREATE TABLE IF NOT EXISTS cases (
                        case_id VARCHAR(255) PRIMARY KEY,
                        title TEXT NOT NULL,
                        symptom TEXT NOT NULL,
                        service_name VARCHAR(255) NOT NULL,
                        source VARCHAR(255) NOT NULL,
                        status VARCHAR(64) NOT NULL,
                        selected_skills JSON,
                        steps JSON,
                        metadata JSON,
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def put(self, case: CaseRecord) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO cases
                    (case_id, title, symptom, service_name, source, status,
                     selected_skills, steps, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
                row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_case(row)

    def list_all(self) -> list[CaseRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM cases ORDER BY updated_at DESC")
                rows = cur.fetchall()
        return [self._row_to_case(row) for row in rows]

    def count(self) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM cases")
                row = cur.fetchone()
        return int(row[0] if row else 0)

    def _row_to_case(self, row: tuple) -> CaseRecord:
        from rootseeker.contracts.case import CaseStatus, CaseStep

        return CaseRecord(
            case_id=row[0],
            title=row[1],
            symptom=row[2],
            service_name=row[3],
            source=row[4],
            status=CaseStatus(row[5]),
            selected_skills=decode_mysql_json(row[6], default=[]),
            steps=[
                CaseStep.model_validate(s) for s in decode_mysql_json(row[7], default=[])
            ],
            metadata=decode_mysql_json(row[8], default={}),
            created_at=datetime.fromisoformat(row[9]),
            updated_at=datetime.fromisoformat(row[10]),
        )


@dataclass
class MysqlEvidenceStore:
    """MySQL-backed evidence store."""

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
                    CREATE TABLE IF NOT EXISTS evidence_packs (
                        case_id VARCHAR(255) PRIMARY KEY,
                        summary TEXT,
                        items JSON,
                        created_at VARCHAR(64)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def put_pack(self, pack: EvidencePack) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO evidence_packs
                    (case_id, summary, items, created_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        pack.case_id,
                        pack.summary,
                        json.dumps([i.model_dump(mode="json") for i in pack.items]),
                        utc_now().isoformat(),
                    ),
                )

    def get_pack(self, case_id: str) -> EvidencePack | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM evidence_packs WHERE case_id = %s", (case_id,))
                row = cur.fetchone()
        if row is None:
            return None
        from rootseeker.contracts.evidence import EvidenceItem

        items = [
            EvidenceItem.model_validate(i) for i in decode_mysql_json(row[2], default=[])
        ]
        return EvidencePack(case_id=row[0], summary=row[1] or "", items=items)


@dataclass
class MysqlReportStore:
    """MySQL-backed report store."""

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
                    CREATE TABLE IF NOT EXISTS reports (
                        case_id VARCHAR(255) PRIMARY KEY,
                        title TEXT,
                        summary TEXT,
                        root_cause JSON,
                        evidence_item_ids JSON,
                        metadata JSON,
                        generated_at VARCHAR(64)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                    """
                )

    def put(self, report: CaseReport) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    REPLACE INTO reports
                    (case_id, title, summary, root_cause, evidence_item_ids, metadata, generated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
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
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM reports WHERE case_id = %s", (case_id,))
                row = cur.fetchone()
        if row is None:
            return None
        from rootseeker.contracts.report import RootCauseConclusion

        root_cause = None
        if row[3]:
            root_cause = RootCauseConclusion.model_validate(decode_mysql_json(row[3]))

        return CaseReport(
            case_id=row[0],
            title=row[1],
            summary=row[2] or "",
            root_cause=root_cause,
            evidence_item_ids=decode_mysql_json(row[4], default=[]),
            metadata=decode_mysql_json(row[5], default={}),
            generated_at=datetime.fromisoformat(row[6]),
        )
