from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scripts.setup import ui
from scripts.setup.env_writer import merge_env_file
from scripts.setup.health import wait_http_ok
from scripts.setup.state import SetupState


def _prepare_zoekt(repo_root: Path) -> None:
    index_bin = repo_root / "docker" / "bin" / "zoekt-index"
    web_bin = repo_root / "docker" / "bin" / "zoekt-webserver"
    if index_bin.exists() and web_bin.exists():
        return
    if os.name == "nt":
        script = repo_root / "docker" / "prepare-zoekt.ps1"
        if script.exists():
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script),
                ],
                cwd=str(repo_root),
                check=False,
            )
            return
    script = repo_root / "docker" / "prepare-zoekt.sh"
    if script.exists():
        subprocess.run(["bash", str(script)], cwd=str(repo_root), check=False)


def run_docker_path(
    repo_root: Path,
    *,
    build_only: bool,
    storage: str,
    state: SetupState,
    noninteractive: bool,
) -> int:
    env_path = repo_root / ".env"
    template = repo_root / ".env.docker"
    if not env_path.exists() and template.exists():
        env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        ui.ok("已从 .env.docker 创建 .env")

    if storage == "sqlite":
        updates = {
            "ROOTSEEKER_STORAGE_BACKEND": "sqlite",
            "COMPOSE_PROFILES": "",
        }
    else:
        updates = {
            "ROOTSEEKER_STORAGE_BACKEND": "mysql",
            "COMPOSE_PROFILES": "mysql",
            "ROOTSEEKER_MYSQL_HOST": "mysql",
            "ROOTSEEKER_MYSQL_PORT": "3306",
            "ROOTSEEKER_MYSQL_USER": "rootseeker",
            "ROOTSEEKER_MYSQL_PASSWORD": "rootseeker",
            "ROOTSEEKER_MYSQL_DATABASE": "rootseeker",
        }
    merge_env_file(env_path, updates, overwrite_existing=True)
    ui.ok(f"已配置存储: {storage}")

    if not noninteractive:
        llm_key = ui.ask("可选：填写 ROOTSEEKER_LLM_API_KEY（回车跳过）", "")
        if llm_key:
            merge_env_file(env_path, {"ROOTSEEKER_LLM_API_KEY": llm_key}, overwrite_existing=True)

    if not state.is_done("zoekt_bins"):
        ui.info("准备 Zoekt 二进制（如需要）...")
        _prepare_zoekt(repo_root)
        state.mark_done("zoekt_bins")

    env = os.environ.copy()
    # Ensure compose picks up profiles from .env
    if storage == "sqlite":
        env["COMPOSE_PROFILES"] = ""
    else:
        env["COMPOSE_PROFILES"] = "mysql"

    ui.info("开始 docker compose build...")
    build = subprocess.run(
        ["docker", "compose", "build"],
        cwd=str(repo_root),
        env=env,
        check=False,
    )
    if build.returncode != 0:
        ui.error("docker compose build 失败")
        return build.returncode

    if build_only:
        ui.ok("仅编译完成（未启动）")
        state.mark_done("docker_up", {"build_only": True})
        return 0

    ui.info("启动服务 docker compose up -d --build ...")
    up = subprocess.run(
        ["docker", "compose", "up", "-d", "--build"],
        cwd=str(repo_root),
        env=env,
        check=False,
    )
    if up.returncode != 0:
        ui.error("docker compose up 失败")
        return up.returncode

    ui.info("等待健康检查...")
    api_ok = wait_http_ok("http://127.0.0.1:8000/healthz", timeout_seconds=180)
    admin_ok = wait_http_ok("http://127.0.0.1:8010/healthz", timeout_seconds=60)
    if not api_ok:
        ui.warn("API 健康检查超时，请稍后执行: docker compose logs -f api")
    else:
        ui.ok("API 健康检查通过 http://127.0.0.1:8000")
    if admin_ok:
        ui.ok("Admin 健康检查通过 http://127.0.0.1:8010/admin")
    else:
        ui.warn("Admin 尚未就绪，可稍后访问 http://127.0.0.1:8010/admin")

    state.mark_done("docker_up", {"storage": storage})
    ui.info("常用命令：")
    ui.info("  docker compose logs -f api")
    ui.info("  ./start.sh stop   或   start.bat stop")
    return 0 if api_ok else 1
