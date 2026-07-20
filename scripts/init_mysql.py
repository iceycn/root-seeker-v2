#!/usr/bin/env python3
"""Apply mysql/init/*.sql against a MySQL database (Docker or custom).

Examples:
  python scripts/init_mysql.py
  python scripts/init_mysql.py --host db.example.com --user app --password secret --database rootseeker
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _split_sql(script: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        buf.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
    trailing = "\n".join(buf).strip()
    if trailing:
        statements.append(trailing)
    return statements


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize RootSeeker MySQL schema")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--database", default=None)
    parser.add_argument(
        "--init-dir",
        default=None,
        help="Directory of *.sql files (default: <repo>/mysql/init)",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    sys.path.insert(0, str(root))

    from rootseeker.infra_core.settings import RootSeekerSettings
    from rootseeker.storage.mysql_conn import connect_mysql, mysql_config_from_settings

    settings = RootSeekerSettings()
    config = mysql_config_from_settings(settings)
    if args.host:
        config = type(config)(
            host=args.host,
            port=args.port or config.port,
            user=args.user or config.user,
            password=args.password if args.password is not None else config.password,
            database=args.database or config.database,
            charset=config.charset,
        )
    else:
        if args.port is not None or args.user or args.password is not None or args.database:
            config = type(config)(
                host=config.host,
                port=args.port or config.port,
                user=args.user or config.user,
                password=args.password if args.password is not None else config.password,
                database=args.database or config.database,
                charset=config.charset,
            )

    init_dir = Path(args.init_dir) if args.init_dir else root / "mysql" / "init"
    if not init_dir.is_dir():
        print(f"init dir not found: {init_dir}", file=sys.stderr)
        return 1

    sql_files = sorted(init_dir.glob("*.sql"))
    if not sql_files:
        print(f"no *.sql files in {init_dir}", file=sys.stderr)
        return 1

    conn = connect_mysql(config)
    try:
        with conn.cursor() as cur:
            for path in sql_files:
                print(f"applying {path.name} ...")
                for stmt in _split_sql(path.read_text(encoding="utf-8")):
                    cur.execute(stmt)
        print(f"ok: applied {len(sql_files)} file(s) to {config.host}/{config.database}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
