from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.setup.env_writer import merge_env_file


def probe_mysql(host: str, port: int, user: str, password: str, database: str) -> tuple[bool, str]:
    try:
        import pymysql
    except ImportError:
        return False, "未安装 PyMySQL，请先完成 pip 依赖安装"
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=5,
        )
        conn.close()
        return True, "连通成功"
    except Exception as exc:  # noqa: BLE001
        return False, f"连通失败: {exc}"


def configure_existing_mysql(
    repo_root: Path,
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
) -> int:
    ok, msg = probe_mysql(host, port, user, password, database)
    if not ok:
        print(f"[错误] {msg}", file=sys.stderr)
        return 1
    merge_env_file(
        repo_root / ".env",
        {
            "ROOTSEEKER_STORAGE_BACKEND": "mysql",
            "ROOTSEEKER_MYSQL_HOST": host,
            "ROOTSEEKER_MYSQL_PORT": str(port),
            "ROOTSEEKER_MYSQL_USER": user,
            "ROOTSEEKER_MYSQL_PASSWORD": password,
            "ROOTSEEKER_MYSQL_DATABASE": database,
        },
        overwrite_existing=True,
    )
    init = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "init_mysql.py"),
            "--host",
            host,
            "--port",
            str(port),
            "--user",
            user,
            "--password",
            password,
            "--database",
            database,
        ],
        cwd=str(repo_root),
        check=False,
    )
    return init.returncode
