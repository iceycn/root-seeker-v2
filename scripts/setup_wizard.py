from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is importable when launched as `python scripts/setup_wizard.py`.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RootSeeker 首次安装向导")
    parser.add_argument("--yes", action="store_true", help="非交互模式")
    parser.add_argument("--path", choices=["docker", "native"], default=None)
    parser.add_argument(
        "--storage",
        choices=["mysql", "sqlite", "existing-mysql"],
        default=None,
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    return parser.parse_args(argv)


def _repo_root() -> Path:
    return _REPO_ROOT


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = _repo_root()
    state_path = root / ".setup-state.json"

    if args.yes and args.path is None and not args.status and not args.resume:
        print("[错误] --yes 模式必须提供 --path docker|native", file=sys.stderr)
        return 2

    from scripts.setup import ui
    from scripts.setup.detect import detect_environment
    from scripts.setup.state import SetupState

    if args.yes:
        import os

        os.environ["ROOTSEEKER_SETUP_NONINTERACTIVE"] = "1"

    state = SetupState.load(state_path)

    if args.status:
        ui.info(f"进度文件: {state_path}")
        for step in ("detect", "docker_up", "native_runtime", "storage", "indexers", "app_up"):
            status = "已完成" if state.is_done(step) else "未完成"
            ui.info(f"  - {step}: {status}")
        return 0

    try:
        return _run_wizard(root, state, state_path, args)
    except KeyboardInterrupt:
        state.save(state_path)
        ui.warn("已中断，进度已保存。续跑：python scripts/setup_wizard.py --resume")
        return 130


def _run_wizard(root: Path, state, state_path: Path, args) -> int:
    from scripts.setup import ui
    from scripts.setup.detect import detect_environment
    from scripts.setup.docker_path import run_docker_path
    from scripts.setup.native_path import run_native_path

    ui.info("欢迎使用 RootSeeker V2 安装向导")
    env = detect_environment(root)
    if not args.resume or not state.is_done("detect"):
        ui.info(f"操作系统: {env.os_name}")
        ui.info(f"Python: {env.python_version} ({'OK' if env.python_ok else '需要 >= 3.11'})")
        ui.info(f"Docker CLI: {'有' if env.docker_cli else '无'}")
        ui.info(f"Docker Daemon: {'可用' if env.docker_daemon else '不可用'}")
        state.mark_done(
            "detect",
            {
                "os": env.os_name,
                "python": env.python_version,
                "docker_daemon": env.docker_daemon,
            },
        )
        state.save(state_path)

    if not env.python_ok:
        ui.error("需要 Python 3.11 或更高版本")
        return 1

    default_path = "docker" if env.docker_daemon else "native"
    path = args.path or ui.choose(
        "请选择安装路径：",
        [
            ("docker", "Docker 全栈（推荐，若本机 Docker 可用）"),
            ("native", "本机完整安装（无 Docker 或需要本机开发）"),
        ],
        default_path,
    )

    if path == "docker":
        if not env.docker_daemon:
            ui.error("未检测到可用的 Docker Daemon，无法走 Docker 路径")
            return 1
        storage = args.storage or "mysql"
        if storage == "existing-mysql":
            storage = "mysql"
        code = run_docker_path(
            root,
            build_only=bool(args.build_only),
            storage=storage if storage in {"mysql", "sqlite"} else "mysql",
            state=state,
            noninteractive=bool(args.yes),
        )
        state.save(state_path)
        return code

    storage = args.storage
    if storage is None:
        storage = ui.choose(
            "请选择数据存储方式：",
            [
                ("sqlite", "内置 SQLite（最简单）"),
                ("mysql", "下载便携 MySQL 到项目目录（.tools）"),
                ("existing-mysql", "使用本机已安装的 MySQL"),
            ],
            "sqlite",
        )
    code = run_native_path(
        root,
        storage=storage,
        state=state,
        noninteractive=bool(args.yes),
    )
    state.save(state_path)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
