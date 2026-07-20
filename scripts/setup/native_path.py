from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

from scripts.setup import ui
from scripts.setup.env_writer import merge_env_file
from scripts.setup.existing_mysql import configure_existing_mysql
from scripts.setup.health import wait_http_ok
from scripts.setup.indexers import setup_indexers
from scripts.setup.portable_mysql import ensure_portable_mysql
from scripts.setup.state import SetupState


def ensure_venv(repo_root: Path) -> Path:
    venv_dir = repo_root / ".venv"
    if os.name == "nt":
        python = venv_dir / "Scripts" / "python.exe"
    else:
        python = venv_dir / "bin" / "python"
    if not python.exists():
        ui.info("创建虚拟环境 .venv ...")
        venv.create(venv_dir, with_pip=True)
    return python


def pip_install_project(python: Path, repo_root: Path) -> int:
    ui.info("安装项目依赖 pip install -e \".[dev]\" ...")
    upgrade = subprocess.run(
        [str(python), "-m", "pip", "install", "-U", "pip"],
        cwd=str(repo_root),
        check=False,
    )
    if upgrade.returncode != 0:
        return upgrade.returncode
    return subprocess.run(
        [str(python), "-m", "pip", "install", "-e", ".[dev]"],
        cwd=str(repo_root),
        check=False,
    ).returncode


def configure_sqlite(repo_root: Path) -> None:
    merge_env_file(
        repo_root / ".env",
        {
            "ROOTSEEKER_STORAGE_BACKEND": "sqlite",
            "ROOTSEEKER_SQLITE_DB_PATH": "data/rootseeker.db",
        },
        overwrite_existing=True,
    )


def start_uvicorn(
    python: Path,
    repo_root: Path,
    *,
    module: str,
    port: int,
    pid_key: str,
    state: SetupState,
) -> None:
    log_dir = repo_root / ".tools" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{pid_key}.log"
    cmd = [
        str(python),
        "-m",
        "uvicorn",
        module,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
    stdout = open(log_file, "a", encoding="utf-8")  # noqa: SIM115
    kwargs: dict = {
        "cwd": str(repo_root),
        "stdout": stdout,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    meta = state.meta("app_up")
    meta[pid_key] = proc.pid
    state.set_meta("app_up", meta)


def run_native_path(
    repo_root: Path,
    *,
    storage: str,
    state: SetupState,
    noninteractive: bool,
) -> int:
    if not state.is_done("native_runtime"):
        python = ensure_venv(repo_root)
        code = pip_install_project(python, repo_root)
        if code != 0:
            ui.error("依赖安装失败")
            return code
        state.mark_done("native_runtime", {"python": str(python)})
    else:
        python = Path(state.meta("native_runtime").get("python") or ensure_venv(repo_root))

    if not state.is_done("storage"):
        if storage == "sqlite":
            configure_sqlite(repo_root)
            ui.ok("已配置 SQLite")
        elif storage == "mysql":
            ok_flag, msg = ensure_portable_mysql(repo_root, port=3307)
            if not ok_flag:
                ui.error(msg)
                if noninteractive or not ui.confirm("便携 MySQL 失败，是否改用 SQLite？", True):
                    return 1
                configure_sqlite(repo_root)
                storage = "sqlite"
                ui.ok("已降级为 SQLite")
            else:
                ui.ok(msg)
        elif storage == "existing-mysql":
            from scripts.setup import ui as _ui

            host = _ui.ask("MySQL 主机", "127.0.0.1")
            port_s = _ui.ask("MySQL 端口", "3306")
            user = _ui.ask("MySQL 用户", "rootseeker")
            password = _ui.ask("MySQL 密码", "rootseeker")
            database = _ui.ask("MySQL 数据库", "rootseeker")
            code = configure_existing_mysql(
                repo_root,
                host=host,
                port=int(port_s or "3306"),
                user=user,
                password=password,
                database=database,
            )
            if code != 0:
                return code
            ui.ok("已配置已有 MySQL")
        else:
            ui.error(f"未知存储类型: {storage}")
            return 2
        state.mark_done("storage", {"storage": storage})

    if not state.is_done("indexers"):
        summary = setup_indexers(repo_root, state, noninteractive=noninteractive)
        for name, status in summary.items():
            ui.info(f"索引组件 {name}: {status}")
        state.mark_done("indexers", summary)

    if not state.is_done("app_up"):
        start_uvicorn(
            python,
            repo_root,
            module="apps.api.main:app",
            port=8000,
            pid_key="api_pid",
            state=state,
        )
        start_uvicorn(
            python,
            repo_root,
            module="apps.admin.main:app",
            port=8010,
            pid_key="admin_pid",
            state=state,
        )
        ui.info("等待本机服务健康检查...")
        api_ok = wait_http_ok("http://127.0.0.1:8000/healthz", timeout_seconds=90)
        admin_ok = wait_http_ok("http://127.0.0.1:8010/healthz", timeout_seconds=60)
        state.mark_done("app_up", state.meta("app_up"))
        if api_ok:
            ui.ok("API: http://127.0.0.1:8000")
        else:
            ui.warn("API 未在超时内就绪，日志见 .tools/logs/api_pid.log")
        if admin_ok:
            ui.ok("Admin: http://127.0.0.1:8010/admin")
        else:
            ui.warn("Admin 未在超时内就绪，日志见 .tools/logs/admin_pid.log")
        ui.info("Hybrid 快捷：.\\\\scripts\\\\start-local.ps1")
        return 0 if api_ok else 1

    ui.ok("本机安装步骤此前已完成（可用 --status 查看）")
    return 0
