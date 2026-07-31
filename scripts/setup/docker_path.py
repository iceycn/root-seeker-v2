from __future__ import annotations

import os
import subprocess
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


def _compose_cmd(repo_root: Path, *, use_pull: bool) -> list[str]:
    cmd = ["docker", "compose", "-f", str(repo_root / "docker-compose.yml")]
    if use_pull:
        pull_file = repo_root / "docker-compose.pull.yml"
        if pull_file.exists():
            cmd.extend(["-f", str(pull_file)])
    return cmd


def _image_present(name: str) -> bool:
    probe = subprocess.run(
        ["docker", "image", "inspect", name],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def _run_pull_stack(repo_root: Path, *, env: dict[str, str], build_only: bool) -> int:
    """Start (or pull) using prebuilt Hub images + compose profiles."""
    base = _compose_cmd(repo_root, use_pull=True)
    hub_user = env.get("DOCKERHUB_USER", "wuhun0301")
    app_image = f"docker.io/{hub_user}/rootseeker-v2:latest"
    mysql_image = env.get("MYSQL_IMAGE", "mysql:8.0")

    if build_only:
        ui.info("预构建模式：拉取镜像（不启动）...")
        pull = subprocess.run([*base, "pull"], cwd=str(repo_root), env=env, check=False)
        return pull.returncode

    # Prefer local images when Hub is flaky.
    pull_flag = ["--pull", "never"] if _image_present(app_image) else ["--pull", "missing"]
    if not _image_present(mysql_image) and not _image_present("mysql:8.0"):
        ui.warn(
            f"未找到本地 MySQL 镜像（{mysql_image}）。"
            "可先执行: docker pull mysql:8.0"
            " 或设置 MYSQL_IMAGE 为可用镜像源后重试。"
        )

    ui.info("使用预构建镜像启动: docker compose -f ...pull.yml up -d ...")
    up = subprocess.run(
        [*base, "up", "-d", *pull_flag],
        cwd=str(repo_root),
        env=env,
        check=False,
    )
    return up.returncode


def run_docker_path(
    repo_root: Path,
    *,
    build_only: bool,
    storage: str,
    state: SetupState,
    noninteractive: bool,
    use_pull: bool = False,
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
    env.setdefault("DOCKERHUB_USER", os.environ.get("DOCKERHUB_USER", "wuhun0301"))

    from scripts.setup.mirrors import apply_cn_docker_env, is_cn_region, setup_region

    ui.info(f"安装区域: {setup_region()}（国内请用 setup-cn.ps1 / setup-cn.sh）")
    env = apply_cn_docker_env(env)

    prefer_pull = use_pull or os.environ.get("ROOTSEEKER_SETUP_DOCKER_PULL", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    # 国内默认优先预构建+加速拉镜像，减少本地 build 踩 Hub/apt。
    if is_cn_region() and not use_pull and os.environ.get("ROOTSEEKER_SETUP_FORCE_BUILD", "").strip() not in {
        "1",
        "true",
        "yes",
    }:
        prefer_pull = True
        ui.info("国内模式默认走预构建镜像拉取（可用 ROOTSEEKER_SETUP_FORCE_BUILD=1 强制本地 build）")

    up_code = 1
    mode = "build"
    if prefer_pull:
        mode = "pull"
        ui.info("已选择预构建镜像路径（跳过本地 build）")
        up_code = _run_pull_stack(repo_root, env=env, build_only=build_only)
        if up_code != 0:
            ui.error("预构建镜像启动/拉取失败")
            return up_code
        if build_only:
            ui.ok("预构建镜像拉取完成（未启动）")
            state.mark_done("docker_up", {"build_only": True, "mode": "pull"})
            return 0
    else:
        ui.info("开始 docker compose build...")
        build = subprocess.run(
            [*_compose_cmd(repo_root, use_pull=False), "build"],
            cwd=str(repo_root),
            env=env,
            check=False,
        )
        if build.returncode != 0:
            ui.warn("docker compose build 失败，尝试回退到预构建镜像（docker-compose.pull.yml）...")
            mode = "pull-fallback"
            up_code = _run_pull_stack(repo_root, env=env, build_only=build_only)
            if up_code != 0:
                ui.error(
                    "本地 build 与预构建回退均失败。"
                    "国内可改用 setup-cn.ps1 / setup-cn.sh；"
                    "或手动拉取: docker pull docker.m.daocloud.io/library/mysql:8.0"
                    " 并 docker tag ... mysql:8.0。"
                )
                return up_code
            if build_only:
                ui.ok("已通过预构建镜像完成（未启动）")
                state.mark_done("docker_up", {"build_only": True, "mode": mode})
                return 0
        else:
            if build_only:
                ui.ok("仅编译完成（未启动）")
                state.mark_done("docker_up", {"build_only": True, "mode": "build"})
                return 0
            ui.info("启动服务 docker compose up -d --build ...")
            up = subprocess.run(
                [*_compose_cmd(repo_root, use_pull=False), "up", "-d", "--build"],
                cwd=str(repo_root),
                env=env,
                check=False,
            )
            up_code = up.returncode
            if up_code != 0:
                ui.warn("docker compose up --build 失败，尝试预构建镜像回退...")
                mode = "pull-fallback"
                up_code = _run_pull_stack(repo_root, env=env, build_only=False)

    if up_code != 0:
        ui.error("docker compose up 失败")
        return up_code

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

    state.mark_done("docker_up", {"storage": storage, "mode": mode})
    ui.info("常用命令：")
    ui.info("  docker compose logs -f api")
    ui.info("  ./start.sh stop   或   start.bat stop")
    return 0 if api_ok else 1
