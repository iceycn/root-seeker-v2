from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure repo root is importable when launched as `python scripts/uninstall.py`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _repo_root() -> Path:
    return _REPO_ROOT


def _info(msg: str) -> None:
    print(f"[信息] {msg}")


def _ok(msg: str) -> None:
    print(f"[完成] {msg}")


def _warn(msg: str) -> None:
    print(f"[警告] {msg}")


def _kill_pid(pid: int) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], check=False, capture_output=True)
        else:
            os.kill(pid, 15)
    except OSError:
        pass


def stop_native_from_state(repo_root: Path) -> None:
    state_path = repo_root / ".setup-state.json"
    if not state_path.exists():
        return
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, dict):
        return
    app = steps.get("app_up")
    if not isinstance(app, dict):
        return
    meta = app.get("meta") if isinstance(app.get("meta"), dict) else {}
    for key in ("api_pid", "admin_pid"):
        pid = meta.get(key)
        if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()):
            _info(f"停止本机进程 {key}={pid}")
            _kill_pid(int(pid))


def stop_docker_stack(repo_root: Path) -> None:
    compose = repo_root / "docker-compose.yml"
    if not compose.exists():
        return
    env = os.environ.copy()
    env["COMPOSE_PROFILES"] = "mysql"
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose),
        "-f",
        str(repo_root / "docker-compose.pull.yml"),
        "down",
        "-v",
        "--remove-orphans",
    ]
    # pull.yml may be missing in odd checkouts; fall back to base file only.
    if not (repo_root / "docker-compose.pull.yml").exists():
        cmd = ["docker", "compose", "-f", str(compose), "down", "-v", "--remove-orphans"]
    _info("停止并删除 Docker 容器与 volumes ...")
    result = subprocess.run(cmd, cwd=str(repo_root), env=env, check=False)
    if result.returncode != 0:
        # Retry without pull overlay / without daemon noise.
        subprocess.run(
            ["docker", "compose", "-f", str(compose), "down", "-v", "--remove-orphans"],
            cwd=str(repo_root),
            env=env,
            check=False,
        )


def _rm_path(path: Path) -> None:
    if not path.exists():
        return
    _info(f"删除 {path}")
    if path.is_file() or path.is_symlink():
        try:
            path.unlink()
        except OSError as exc:
            _warn(f"无法删除文件 {path}: {exc}")
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        _warn(f"无法删除目录 {path}: {exc}")


def clean_local_artifacts(repo_root: Path) -> None:
    for name in (
        ".tools",
        ".venv",
        "venv",
        ".setup-state.json",
        ".env",
        ".env.bak-smoke",
        ".env.local",
    ):
        _rm_path(repo_root / name)

    data_dir = repo_root / "data"
    if data_dir.is_dir():
        _info(f"清空 {data_dir}")
        for child in data_dir.iterdir():
            _rm_path(child)

    # Wizard / smoke logs sometimes land here
    for pattern in (".setup-state-*.json", ".env-*.tmp"):
        for path in repo_root.glob(pattern):
            _rm_path(path)


def run_uninstall(repo_root: Path | None = None) -> int:
    root = repo_root or _repo_root()
    _info(f"开始卸载清理: {root}")

    stop_native_from_state(root)
    try:
        from scripts.setup.portable_mysql import stop_portable_mysql

        stop_portable_mysql(root)
        _ok("已停止便携 MySQL（若在运行）")
    except Exception as exc:  # noqa: BLE001
        _warn(f"停止便携 MySQL 时出错: {exc}")

    try:
        stop_docker_stack(root)
        _ok("Docker 栈已 down -v")
    except Exception as exc:  # noqa: BLE001
        _warn(f"Docker 清理跳过/失败: {exc}")

    clean_local_artifacts(root)
    _ok("本地安装产物已清理（含 .env / .venv / .tools / data / 进度文件）")
    _info("源代码与已拉取的 Docker 镜像保留；需要镜像也可自行 docker image prune")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RootSeeker 卸载：停止服务并清理全部安装产物")
    parser.parse_args(argv)
    return run_uninstall()


if __name__ == "__main__":
    raise SystemExit(main())
