"""Clear case/evidence/checkpoint tables in rootseeker.db (no backup)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rootseeker.storage import (
    SqliteCaseStore,
    SqliteCheckpointStore,
    SqliteEvidenceStore,
    SqliteReportStore,
    SqliteTaskStore,
)


TABLES = ("evidence_packs", "cases", "reports", "checkpoints", "tasks")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    db_path = root / "data" / "rootseeker.db"

    if not db_path.exists():
        print(f"db missing, creating empty schema at {db_path}")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        SqliteCaseStore(db_path)
        SqliteEvidenceStore(db_path)
        SqliteReportStore(db_path)
        SqliteCheckpointStore(db_path)
        SqliteTaskStore(db_path)
        print("done")
        return

    before = db_path.stat().st_size
    print(f"db size before: {before / 1024**3:.2f} GB")

    # Prefer recreate: reclaim disk immediately without VACUUM of a 15GB file.
    db_path.unlink()
    SqliteCaseStore(db_path)
    SqliteEvidenceStore(db_path)
    SqliteReportStore(db_path)
    SqliteCheckpointStore(db_path)
    SqliteTaskStore(db_path)

    after = db_path.stat().st_size
    print(f"cleared tables: {', '.join(TABLES)}")
    print(f"db size after: {after} bytes")


if __name__ == "__main__":
    main()
