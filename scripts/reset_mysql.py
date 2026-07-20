#!/usr/bin/env python3
"""Truncate RootSeeker MySQL application tables (keeps schema).

Examples:
  python scripts/reset_mysql.py
  python scripts/reset_mysql.py --yes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TABLES = (
    "cases",
    "evidence_packs",
    "reports",
    "tasks",
    "checkpoints",
    "admin_config",
    "cron_job_states",
    "cron_job_runs",
    "error_chat_history",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Truncate RootSeeker MySQL tables")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    from rootseeker.infra_core.settings import RootSeekerSettings
    from rootseeker.storage.mysql_conn import MysqlConnectConfig, connect_mysql, mysql_config_from_settings

    settings = RootSeekerSettings()
    config = mysql_config_from_settings(settings)
    config = MysqlConnectConfig(
        host=args.host or config.host,
        port=args.port or config.port,
        user=args.user or config.user,
        password=args.password if args.password is not None else config.password,
        database=args.database or config.database,
        charset=config.charset,
        connect_timeout=config.connect_timeout,
    )

    if not args.yes:
        reply = input(
            f"Truncate tables in {config.host}:{config.port}/{config.database}? [y/N] "
        ).strip()
        if reply.lower() not in {"y", "yes"}:
            print("aborted")
            return 1

    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for table in TABLES:
                cur.execute(f"TRUNCATE TABLE `{table}`")
                print(f"truncated {table}")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        print("ok")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
